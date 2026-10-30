import pytest
from app.models import Employee, Membership, identifier
from conftest import DEV, HR, ORG_A, ORG_B, OWNER, headers, login


def employee(db):
    record = Employee(
        id=identifier(),
        organization_id=ORG_A,
        user_id=DEV,
        name="Compensation fixture",
        department="Engineering",
        status="active",
        verification_status="approved",
    )
    db.add(record)
    db.commit()
    return record


def propose(client, record, **values):
    login(HR)
    response = client.post(
        "/api/v1/hr/lifecycle",
        headers=headers(),
        json={"employee_id": record.id, "kind": "transfer", "department": "Platform", **values},
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def approve(client, plan):
    login(OWNER)
    response = client.post(
        f"/api/v1/hr/lifecycle/{plan}/decision", headers=headers(), json={"decision": "approved"}
    )
    assert response.status_code == 200, response.text
    login(HR)


def test_inverse_plan_needs_fresh_approval_and_preserves_original_history(client, db):
    record = employee(db)
    original = propose(client, record)
    approve(client, original)
    base = f"/api/v1/hr/lifecycle/{original}"
    assert client.post(base + "/execute", headers=headers()).status_code == 200
    assert db.get(Employee, record.id).department == "Platform"
    response = client.post(
        base + "/compensation",
        headers=headers(),
        json={"reason": "Reverse the reviewed department change"},
    )
    assert response.status_code == 201, response.text
    replacement = response.json()
    assert (
        replacement["status"] == "proposed" and replacement["snapshot"]["department"] == "Platform"
    )
    assert replacement["proposed"]["department"] == "Engineering"
    assert db.get(Employee, record.id).department == "Platform"
    again = client.post(
        base + "/compensation", headers=headers(), json={"reason": "Repeated inverse request"}
    )
    assert again.json()["id"] == replacement["id"]
    inverse = f"/api/v1/hr/lifecycle/{replacement['id']}"
    assert client.post(inverse + "/execute", headers=headers()).status_code == 409
    approve(client, replacement["id"])
    assert client.post(inverse + "/execute", headers=headers()).status_code == 200
    assert db.get(Employee, record.id).department == "Engineering"
    source = client.get(base, headers=headers()).json()
    assert source["status"] == "completed"
    assert any(item["action"] == "compensation_proposed" for item in source["history"])


@pytest.mark.parametrize("change", ["inactive", "role_changed"])
def test_execution_rechecks_independent_approver_authority(client, db, change):
    record = employee(db)
    plan = propose(client, record)
    approve(client, plan)
    owner = db.get(Membership, (ORG_A, OWNER))
    if change == "inactive":
        owner.active = False
    else:
        owner.role = "junior_developer"
    db.commit()
    response = client.post(f"/api/v1/hr/lifecycle/{plan}/execute", headers=headers())
    assert response.status_code == 409
    assert db.get(Employee, record.id).department == "Engineering"


def test_compensation_cannot_restore_offboarded_access_or_overwrite_later_changes(client, db):
    record = employee(db)
    plan = propose(client, record)
    approve(client, plan)
    assert client.post(f"/api/v1/hr/lifecycle/{plan}/execute", headers=headers()).status_code == 200
    record.department = "Later independently assigned department"
    db.commit()
    reason = {"reason": "Attempt inverse on changed employee"}
    assert (
        client.post(
            f"/api/v1/hr/lifecycle/{plan}/compensation", headers=headers(), json=reason
        ).status_code
        == 409
    )
    offboarding = propose(client, record, kind="offboarding", department=None)
    approve(client, offboarding)
    assert (
        client.post(f"/api/v1/hr/lifecycle/{offboarding}/execute", headers=headers()).status_code
        == 200
    )
    assert (
        client.post(
            f"/api/v1/hr/lifecycle/{offboarding}/compensation", headers=headers(), json=reason
        ).status_code
        == 409
    )
    assert db.get(Membership, (ORG_A, DEV)).active is False


def test_compensation_tenant_and_role_guards(client, db):
    record = employee(db)
    plan = propose(client, record)
    approve(client, plan)
    assert client.post(f"/api/v1/hr/lifecycle/{plan}/execute", headers=headers()).status_code == 200
    route = f"/api/v1/hr/lifecycle/{plan}/compensation"
    reason = {"reason": "Authorized inverse review request"}
    assert client.post(route, headers=headers(ORG_B), json=reason).status_code == 404
    login(OWNER)
    assert client.post(route, headers=headers(), json=reason).status_code == 403
