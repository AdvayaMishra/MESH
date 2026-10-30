from datetime import timedelta

import pytest
from app.cloud_worker import run_once
from app.models import CloudAssessment, CloudAssessmentJob, Membership, identifier, now
from conftest import ANALYST, ORG_A, ORG_B, OWNER, headers, login
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker


def report():
    return {
        "findings": [],
        "errors": [{"check": "fixture", "state": "unknown"}],
        "partial": True,
        "coverage": ["fixture"],
        "limitations": ["Fixture, no live AWS call"],
    }


def job(db, **kwargs):
    record = CloudAssessmentJob(
        id=identifier(),
        organization_id=ORG_A,
        requested_by=ANALYST,
        request_key=identifier(),
        **kwargs,
    )
    db.add(record)
    db.commit()
    return record


def test_cloud_job_api_is_idempotent_analyst_only_and_tenant_scoped(client, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(
        settings(), "aws_role_bindings", {ORG_A: "arn:aws:iam::012345678901:role/fixture-reader"}
    )
    login(ANALYST)
    payload = {"request_key": "cloud-job-fixture"}
    response = client.post("/api/v1/vader/cloud/jobs", headers=headers(), json=payload)
    assert response.status_code == 202, response.text
    job_id = response.json()["id"]
    assert (
        client.post("/api/v1/vader/cloud/jobs", headers=headers(), json=payload).json()["id"]
        == job_id
    )
    assert (
        client.get("/api/v1/vader/cloud/jobs/" + job_id, headers=headers(ORG_B)).status_code == 404
    )
    assert (
        client.post(f"/api/v1/vader/cloud/jobs/{job_id}/cancel", headers=headers()).json()["status"]
        == "cancelled"
    )
    login(OWNER)
    assert client.get("/api/v1/vader/cloud/jobs", headers=headers()).status_code == 403


@pytest.mark.parametrize("revoke", [False, True])
def test_cloud_worker_retains_partial_evidence_and_rechecks_requester_authorization(
    db, monkeypatch, revoke
):
    record = job(db)
    factory = sessionmaker(db.get_bind(), expire_on_commit=False)
    monkeypatch.setattr("app.cloud_worker.SessionFactory", factory)

    def runner(organization):
        assert organization == ORG_A
        if revoke:
            with factory.begin() as session:
                session.get(Membership, (ORG_A, ANALYST)).active = False
        return report()

    assert run_once(ORG_A, runner)
    db.expire_all()
    current = db.get(CloudAssessmentJob, record.id)
    assert current.status == ("cancelled" if revoke else "completed")
    assessments = db.scalars(select(CloudAssessment)).all()
    assert len(assessments) == (0 if revoke else 1)
    if assessments:
        assert assessments[0].partial and assessments[0].errors
        assert current.assessment_id == assessments[0].id
    assert not run_once(ORG_A, runner)


def test_cancelled_lease_discards_late_cloud_worker_output(db, monkeypatch):
    record = job(db)
    factory = sessionmaker(db.get_bind(), expire_on_commit=False)
    monkeypatch.setattr("app.cloud_worker.SessionFactory", factory)

    def runner(_):
        with factory.begin() as session:
            current = session.get(CloudAssessmentJob, record.id)
            current.status, current.lease_until = "cancelled", None
        return report()

    assert run_once(ORG_A, runner)
    assert db.scalars(select(CloudAssessment)).all() == []


def test_cloud_attempt_limit_survives_a_worker_crash_without_a_fourth_provider_call(
    db, monkeypatch
):
    record = job(db, status="running", attempts=3, lease_until=now() - timedelta(minutes=1))
    monkeypatch.setattr(
        "app.cloud_worker.SessionFactory", sessionmaker(db.get_bind(), expire_on_commit=False)
    )
    called = []
    assert run_once(ORG_A, lambda _: called.append(True))
    db.expire_all()
    assert db.get(CloudAssessmentJob, record.id).status == "dead_letter"
    assert not called


def test_invalid_cloud_completeness_retries_then_dead_letters(db, monkeypatch):
    record = job(db)
    factory = sessionmaker(db.get_bind(), expire_on_commit=False)
    monkeypatch.setattr("app.cloud_worker.SessionFactory", factory)
    invalid = {**report(), "partial": False}
    for attempt in range(3):
        if attempt:
            with factory.begin() as session:
                session.get(CloudAssessmentJob, record.id).lease_until = now() - timedelta(
                    seconds=1
                )
        assert run_once(ORG_A, lambda _: invalid)
    db.expire_all()
    current = db.get(CloudAssessmentJob, record.id)
    assert current.status == "dead_letter" and current.attempts == 3
    assert db.scalars(select(CloudAssessment)).all() == []
