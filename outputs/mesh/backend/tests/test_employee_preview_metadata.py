from app.models import Employee, Membership, identifier
from conftest import DEV, HR, ORG_A, ORG_B, OWNER, headers, login


def test_employee_metadata_comes_from_same_tenant_membership(client, db):
    own = db.get(Membership, (ORG_A, DEV))
    foreign = db.get(Membership, (ORG_B, DEV))
    own.email = "local-developer@example.org"
    foreign.email = "foreign-owner@example.org"
    foreign.role = "owner"
    record = Employee(
        id=identifier(),
        organization_id=ORG_A,
        user_id=DEV,
        name="Local Developer",
        department="Engineering",
    )
    db.add(record)
    db.commit()
    login(HR)
    response = client.get("/api/v1/employees", headers=headers())
    assert response.status_code == 200
    value = next(row for row in response.json() if row["id"] == record.id)
    assert value["email"] == "local-developer@example.org"
    assert value["app_role"] == "junior_developer"
    assert value["created_at"]
    detail = client.get(f"/api/v1/employees/{record.id}", headers=headers())
    assert detail.status_code == 200
    assert detail.json() == value
    login(OWNER)
    assert client.get("/api/v1/employees", headers=headers()).status_code == 403
    login(HR)
    assert client.get(f"/api/v1/employees/{record.id}", headers=headers(ORG_B)).status_code == 404
