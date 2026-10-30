from datetime import timedelta

import pytest
from app.models import Finding, Membership, Repository, ScanJob, identifier, now
from app.scan_worker import publish_progress, run_once
from conftest import ANALYST, ORG_A, ORG_B, headers, login
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker


def prepare(db, monkeypatch):
    repository = Repository(
        id=identifier(),
        organization_id=ORG_A,
        full_name="fixture/repository",
        installation_id=1,
        enabled=True,
    )
    db.add(repository)
    db.flush()
    job = ScanJob(
        id=identifier(),
        organization_id=ORG_A,
        repository_id=repository.id,
        requested_by=ANALYST,
        request_key=identifier(),
        commit_sha="a" * 40,
    )
    db.add(job)
    db.commit()
    factory = sessionmaker(db.get_bind(), expire_on_commit=False)
    monkeypatch.setattr("app.scan_worker.SessionFactory", factory)
    monkeypatch.setattr("app.scan_worker.GitHubApp.token", lambda *args: "synthetic-token")
    return job, factory


def test_default_pipeline_persists_pollable_phase_progress_and_committed_completion(
    client, db, monkeypatch
):
    job, factory = prepare(db, monkeypatch)
    observed = []

    def runner(repo, commit, token, progress):
        for stage, finished in [("checkout", []), ("semgrep", ["checkout"])]:
            progress(stage, finished)
            with factory.begin() as reader:
                report = reader.get(ScanJob, job.id).report
                observed.append((report["stage"], report["progress"]))
        return {"completed": ["semgrep", "bandit", "gitleaks", "osv"], "findings": []}

    monkeypatch.setattr("app.scan_worker.scan_repository", runner)
    assert run_once(ORG_A)
    assert observed == [("checkout", 0), ("semgrep", 20)]
    db.expire_all()
    login(ANALYST)
    response = client.get("/api/v1/scans/" + job.id, headers=headers())
    assert response.status_code == 200
    assert response.json()["status"] == "completed"
    assert response.json()["report"]["progress"] == 100


def test_revocation_before_next_phase_cancels_without_saving_findings(db, monkeypatch):
    job, factory = prepare(db, monkeypatch)
    entered = []

    def runner(repo, commit, token, progress):
        progress("checkout", [])
        entered.append(True)
        with factory.begin() as mutation:
            mutation.get(Membership, (ORG_A, ANALYST)).active = False
        progress("semgrep", ["checkout"])
        raise AssertionError("Revoked scan continued")

    monkeypatch.setattr("app.scan_worker.scan_repository", runner)
    assert run_once(ORG_A)
    assert entered == [True]
    db.expire_all()
    assert db.get(ScanJob, job.id).status == "cancelled"
    assert db.get(ScanJob, job.id).report["stage"] == "cancelled"
    assert not db.scalars(select(Finding)).all()


def test_stale_worker_cannot_publish_after_another_lease_takes_ownership(db, monkeypatch):
    job, factory = prepare(db, monkeypatch)

    def runner(repo, commit, token, progress):
        progress("checkout", [])
        with factory.begin() as mutation:
            current = mutation.get(ScanJob, job.id)
            current.lease_until += timedelta(minutes=1)
        progress("semgrep", ["checkout"])
        raise AssertionError("Stale worker continued")

    monkeypatch.setattr("app.scan_worker.scan_repository", runner)
    assert run_once(ORG_A)
    db.expire_all()
    assert db.get(ScanJob, job.id).status == "running"
    assert db.get(ScanJob, job.id).report["stage"] == "checkout"
    assert not db.scalars(select(Finding)).all()


def test_progress_update_cannot_cross_the_organization_boundary(db, monkeypatch):
    job, _ = prepare(db, monkeypatch)
    lease = now() + timedelta(minutes=30)
    job.status, job.lease_until = "running", lease
    job.report = {"stage": "starting", "progress": 0}
    db.commit()
    with pytest.raises(PermissionError):
        publish_progress(ORG_B, job.id, lease, "checkout", [])
    db.expire_all()
    assert db.get(ScanJob, job.id).report == {"stage": "starting", "progress": 0}
