from datetime import timedelta

import pytest
from app.auth import Identity, identity
from app.main import app
from app.models import (
    CloudAssessmentJob,
    Membership,
    Project,
    ProjectMember,
    identifier,
    now,
)
from conftest import DEV, HR, ORG_A, ORG_B, OWNER, headers, login
from test_lifecycle_compensation import approve, employee, propose


def offboard(client, db):
    record = employee(db)
    plan = propose(client, record, kind="offboarding", department=None)
    approve(client, plan)
    assert (
        client.post(f"/api/v1/hr/lifecycle/{plan}/execute", headers=headers()).json()["status"]
        == "completed"
    )
    return record


def prepare_rehire(client, db):
    record = offboard(client, db)
    plan = propose(client, record, kind="rehire", role="junior_developer", department="New team")
    approve(client, plan)
    response = client.post(f"/api/v1/hr/lifecycle/{plan}/execute", headers=headers())
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "reconciliation_required"
    assert not db.get(Membership, (ORG_A, DEV)).active
    return record, plan


def activate(client, plan, **values):
    login(OWNER)
    return client.post(
        f"/api/v1/hr/lifecycle/{plan}/rehire-activation",
        headers=headers(),
        json={
            "reference": "reviewed-external-session-and-access-ticket",
            "provider_sessions_revoked": True,
            "external_access_reviewed": True,
            **values,
        },
    )


def test_rehire_requires_independent_review_and_does_not_restore_old_grants_or_tokens(client, db):
    record, plan = prepare_rehire(client, db)
    project = Project(
        id=identifier(),
        organization_id=ORG_A,
        name="Old confidential project",
        description="Retained history",
        proposer_id=DEV,
    )
    db.add(project)
    db.flush()
    db.add(ProjectMember(organization_id=ORG_A, project_id=project.id, user_id=DEV, manager=True))
    job = CloudAssessmentJob(
        organization_id=ORG_A,
        requested_by=DEV,
        request_key=identifier(),
        status="running",
        lease_until=now() + timedelta(minutes=1),
    )
    db.add(job)
    db.commit()
    before = now() - timedelta(minutes=1)
    result = activate(client, plan)
    assert result.status_code == 200, result.text
    assert result.json()["status"] == "completed"
    member = db.get(Membership, (ORG_A, DEV))
    assert (
        member.active and member.role == "junior_developer" and member.access_not_before is not None
    )
    assert record.department == "New team"
    assert db.query(ProjectMember).filter_by(organization_id=ORG_A, user_id=DEV).count() == 0
    assert db.get(CloudAssessmentJob, job.id).status == "cancelled" and job.lease_until is None
    assert activate(client, plan).json() == result.json()
    login(DEV)
    assert client.get("/api/v1/users/me", headers=headers()).status_code == 401
    for issued in (before, member.access_not_before):
        app.dependency_overrides[identity] = lambda issued=issued: Identity(
            DEV, DEV + "@example.org", issued_at=issued
        )
        assert client.get("/api/v1/users/me", headers=headers()).status_code == 401
    app.dependency_overrides[identity] = lambda: Identity(
        DEV, DEV + "@example.org", issued_at=now() + timedelta(seconds=1)
    )
    assert client.get("/api/v1/users/me", headers=headers()).status_code == 200
    assert client.get(f"/api/v1/projects/{project.id}", headers=headers()).status_code == 404
    assert client.get("/api/v1/projects", headers=headers()).json() == []


@pytest.mark.parametrize("field", ["provider_sessions_revoked", "external_access_reviewed"])
def test_rehire_cannot_activate_without_explicit_external_attestations(client, db, field):
    _, plan = prepare_rehire(client, db)
    assert activate(client, plan, **{field: False}).status_code == 422
    assert not db.get(Membership, (ORG_A, DEV)).active


@pytest.mark.parametrize("change", ["identity", "snapshot", "approver", "suspension"])
def test_rehire_activation_rechecks_prerequisites(client, db, change):
    record, plan = prepare_rehire(client, db)
    if change == "identity":
        record.verification_status = "rejected"
    elif change == "snapshot":
        record.department = "Changed after approval"
    elif change == "approver":
        db.get(Membership, (ORG_A, OWNER)).role = "junior_developer"
    else:
        from app.models import Organization

        db.get(Organization, ORG_A).status = "suspended"
    db.commit()
    assert activate(client, plan).status_code in {403, 409}
    assert not db.get(Membership, (ORG_A, DEV)).active


def test_rehire_cannot_bypass_role_tenant_and_generic_reconcile_controls(client, db):
    _, plan = prepare_rehire(client, db)
    route = f"/api/v1/hr/lifecycle/{plan}/rehire-activation"
    assert (
        client.post(
            route,
            headers=headers(),
            json={
                "reference": "reviewed-ticket",
                "provider_sessions_revoked": True,
                "external_access_reviewed": True,
            },
        ).status_code
        == 403
    )
    login(OWNER)
    assert (
        client.post(
            route,
            headers=headers(ORG_B),
            json={
                "reference": "reviewed-ticket",
                "provider_sessions_revoked": True,
                "external_access_reviewed": True,
            },
        ).status_code
        == 404
    )
    assert (
        client.post(
            f"/api/v1/hr/lifecycle/{plan}/reconcile",
            headers=headers(),
            json={"reference": "generic-attestation"},
        ).status_code
        == 409
    )
    assert not db.get(Membership, (ORG_A, DEV)).active


def test_rehire_needs_completed_offboarding_identity_and_explicit_new_assignments(client, db):
    record = employee(db)
    login(HR)
    body = {
        "employee_id": record.id,
        "kind": "rehire",
        "role": "junior_developer",
        "department": "New team",
    }
    assert client.post("/api/v1/hr/lifecycle", headers=headers(), json=body).status_code == 409
    db.delete(record)
    db.commit()
    record = offboard(client, db)
    login(HR)
    body["employee_id"] = record.id
    for field in ("role", "department"):
        assert (
            client.post(
                "/api/v1/hr/lifecycle", headers=headers(), json={**body, field: None}
            ).status_code
            == 422
        )
    record.verification_status = "rejected"
    db.commit()
    assert client.post("/api/v1/hr/lifecycle", headers=headers(), json=body).status_code == 409
