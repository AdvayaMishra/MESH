from app.models import Employee, Membership, identifier
from conftest import DEV, HR, ORG_A, OWNER, headers, login


def employee(db):
    record = Employee(
        id=identifier(),
        organization_id=ORG_A,
        user_id=DEV,
        name="Recovery fixture",
        department="Engineering",
        status="active",
    )
    db.add(record)
    db.commit()
    return record


def plan(client, employee_id, kind="transfer"):
    login(HR)
    payload = {"employee_id": employee_id, "kind": kind}
    if kind == "transfer":
        payload["department"] = "Platform"
    response = client.post("/api/v1/hr/lifecycle", headers=headers(), json=payload)
    assert response.status_code == 201, response.text
    pid = response.json()["id"]
    login(OWNER)
    assert (
        client.post(
            f"/api/v1/hr/lifecycle/{pid}/decision", headers=headers(), json={"decision": "approved"}
        ).status_code
        == 200
    )
    return pid


def test_stale_approved_lifecycle_plan_can_be_cancelled_then_replaced(client, db):
    record = employee(db)
    pid = plan(client, record.id)
    record.department = "Changed after proposal"
    db.commit()
    login(HR)
    assert client.post(f"/api/v1/hr/lifecycle/{pid}/execute", headers=headers()).status_code == 409
    reason = {"reason": "Cancel stale snapshot and request fresh approval"}
    assert (
        client.post(
            f"/api/v1/hr/lifecycle/{pid}/cancel", headers=headers(), json=reason
        ).status_code
        == 403
    )
    login(OWNER)
    response = client.post(f"/api/v1/hr/lifecycle/{pid}/cancel", headers=headers(), json=reason)
    assert response.status_code == 200 and response.json()["status"] == "cancelled"
    assert db.get(Membership, (ORG_A, DEV)).active
    assert plan(client, record.id) != pid


def test_executed_offboarding_cannot_be_cancelled_to_restore_access(client, db):
    record = employee(db)
    pid = plan(client, record.id, kind="offboarding")
    login(HR)
    assert client.post(f"/api/v1/hr/lifecycle/{pid}/execute", headers=headers()).status_code == 200
    assert not db.get(Membership, (ORG_A, DEV)).active
    login(OWNER)
    response = client.post(
        f"/api/v1/hr/lifecycle/{pid}/cancel",
        headers=headers(),
        json={"reason": "Attempt to cancel applied offboarding"},
    )
    assert response.status_code == 409
    assert not db.get(Membership, (ORG_A, DEV)).active
