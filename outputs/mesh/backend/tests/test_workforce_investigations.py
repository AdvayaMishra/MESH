from datetime import UTC, datetime

from app.models import Employee, Incident, Membership, identifier
from conftest import ANALYST, DEV, HR, ORG_A, ORG_B, OWNER, headers, login


def employee(db, user=DEV, org=ORG_A):
    record = Employee(
        id=identifier(),
        organization_id=org,
        user_id=user,
        name="Fixture employee",
        department="Engineering",
        status="active",
    )
    db.add(record)
    db.commit()
    return record


def role(client, org=ORG_A):
    login(HR)
    response = client.post(
        "/api/v1/hr/job-roles",
        headers=headers(org),
        json={
            "title": "Engineer",
            "grade": "E2",
            "version": 1,
            "currency": "INR",
            "minimum_base": "1000.00",
            "maximum_base": "2000.00",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def propose(client, emp, job):
    login(HR)
    response = client.post(
        "/api/v1/hr/employment-changes",
        headers=headers(),
        json={
            "employee_id": emp,
            "job_role_id": job,
            "base": "1500.00",
            "effective_on": "2030-01-01",
            "reason": "Reviewed promotion",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def second_hr(db):
    uid = identifier()
    db.add(Membership(organization_id=ORG_A, user_id=uid, email=uid + "@example.org", role="hr"))
    db.commit()
    return uid


def test_job_roles_are_versioned_private_and_salary_ranges_are_validated(client):
    job = role(client)
    login(OWNER)
    assert client.get("/api/v1/hr/job-roles", headers=headers()).status_code == 403
    login(HR)
    assert client.get("/api/v1/hr/job-roles", headers=headers(ORG_B)).json() == []
    assert (
        client.patch("/api/v1/hr/job-roles/" + job, headers=headers(), json={}).status_code == 404
    )
    response = client.post(
        "/api/v1/hr/job-roles",
        headers=headers(),
        json={
            "title": "Invalid",
            "grade": "E1",
            "version": 1,
            "currency": "INR",
            "minimum_base": "2000.00",
            "maximum_base": "1000.00",
        },
    )
    assert response.status_code == 422


def test_reviewed_employment_snapshot_drives_payroll_and_replays_safely(client, db, monkeypatch):
    record = employee(db)
    job = role(client)
    change = propose(client, record.id, job)
    decision = f"/api/v1/hr/employment-changes/{change}/decision"
    assert (
        client.post(decision, headers=headers(), json={"decision": "approved"}).status_code == 403
    )
    reviewer = second_hr(db)
    login(reviewer)
    assert (
        client.post(decision, headers=headers(), json={"decision": "approved"}).status_code == 200
    )
    endpoint = f"/api/v1/hr/employment-changes/{change}/apply"
    assert client.post(endpoint, headers=headers()).status_code == 409
    monkeypatch.setattr("app.workforce_api.now", lambda: datetime(2030, 1, 1, tzinfo=UTC))
    applied = client.post(endpoint, headers=headers())
    assert applied.status_code == 200, applied.text
    assert applied.json()["base"] == "1500.00"
    assert client.post(endpoint, headers=headers()).json()["id"] == applied.json()["id"]
    rule = client.post(
        "/api/v1/hr/payroll-rules",
        headers=headers(),
        json={
            "name": "Base only",
            "version": 1,
            "currency": "INR",
            "components": [],
        },
    ).json()["id"]
    payload = {"employee_id": record.id, "rule_id": rule, "period": "2030-01", "base": "1600.00"}
    assert (
        client.post("/api/v1/hr/payroll/compute", headers=headers(), json=payload).status_code
        == 409
    )
    payload["base"] = "1500.00"
    assert (
        client.post("/api/v1/hr/payroll/compute", headers=headers(), json=payload).status_code
        == 201
    )
    assert (
        client.post(
            "/api/v1/hr/payroll",
            headers=headers(),
            json={
                "employee_id": record.id,
                "period": "2030-02",
                "currency": "INR",
                "gross": "1800.00",
                "deductions": "100.00",
            },
        ).status_code
        == 409
    )
    login(OWNER)
    assert (
        client.get(
            f"/api/v1/hr/employees/{record.id}/employment-terms", headers=headers()
        ).status_code
        == 403
    )


def test_revoked_hr_reviewer_prevents_employment_application(client, db, monkeypatch):
    record = employee(db)
    job_role = role(client)
    change = propose(client, record.id, job_role)
    reviewer = second_hr(db)
    login(reviewer)
    assert (
        client.post(
            f"/api/v1/hr/employment-changes/{change}/decision",
            headers=headers(),
            json={"decision": "approved"},
        ).status_code
        == 200
    )
    db.get(Membership, (ORG_A, reviewer)).active = False
    db.commit()
    monkeypatch.setattr("app.workforce_api.now", lambda: datetime(2030, 1, 1, tzinfo=UTC))
    login(HR)
    assert (
        client.post(f"/api/v1/hr/employment-changes/{change}/apply", headers=headers()).status_code
        == 409
    )
    response = client.post(
        f"/api/v1/hr/employment-changes/{change}/withdraw",
        headers=headers(),
        json={"reason": "Withdraw stale approval for new review"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "rejected" and response.json()["resolution_reason"]
    assert propose(client, record.id, job_role) != change


def test_salary_proposals_reject_foreign_roles_and_out_of_range_or_midmonth_pay(client, db):
    record = employee(db)
    foreign = role(client, ORG_B)
    login(HR)
    payload = {
        "employee_id": record.id,
        "job_role_id": foreign,
        "base": "1500.00",
        "effective_on": "2030-01-01",
        "reason": "Fixture",
    }
    assert (
        client.post("/api/v1/hr/employment-changes", headers=headers(), json=payload).status_code
        == 404
    )
    payload["job_role_id"] = role(client)
    payload["base"] = "9999.00"
    assert (
        client.post("/api/v1/hr/employment-changes", headers=headers(), json=payload).status_code
        == 422
    )
    payload.update(base="1500.00", effective_on="2030-01-15")
    assert (
        client.post("/api/v1/hr/employment-changes", headers=headers(), json=payload).status_code
        == 422
    )


def test_leave_allowance_reserves_pending_days_and_cancellation_releases_them(client, db):
    record = employee(db)
    endpoint = f"/api/v1/hr/employees/{record.id}/leave-allowance/2026"
    login(HR)
    assert client.put(endpoint, headers=headers(), json={"allowance_days": 2}).status_code == 200
    login(DEV)
    data = {
        "employee_id": record.id,
        "starts_on": "2026-11-02",
        "ends_on": "2026-11-03",
        "reason": "Fixture",
    }
    response = client.post("/api/v1/hr/leave", headers=headers(), json=data)
    assert response.status_code == 201, response.text
    leave = response.json()["id"]
    assert client.get(endpoint, headers=headers()).json()["remaining_days"] == 0
    data.update(starts_on="2026-11-04", ends_on="2026-11-04")
    assert client.post("/api/v1/hr/leave", headers=headers(), json=data).status_code == 409
    assert client.post(f"/api/v1/hr/leave/{leave}/cancel", headers=headers()).status_code == 200
    assert client.get(endpoint, headers=headers()).json()["remaining_days"] == 2
    assert client.post("/api/v1/hr/leave", headers=headers(), json=data).status_code == 201
    login(HR)
    assert client.put(endpoint, headers=headers(), json={"allowance_days": 0}).status_code == 409
    login(OWNER)
    assert client.get(endpoint, headers=headers()).status_code == 403


def test_cross_year_leave_requires_both_years_and_tenant_scope(client, db):
    record = employee(db)
    login(HR)
    endpoint = f"/api/v1/hr/employees/{record.id}/leave-allowance/"
    assert (
        client.put(
            endpoint + "2026", headers=headers(), json={"allowance_days": 1, "counting": "calendar"}
        ).status_code
        == 200
    )
    login(DEV)
    data = {
        "employee_id": record.id,
        "starts_on": "2026-12-31",
        "ends_on": "2027-01-01",
        "reason": "Fixture",
    }
    assert client.post("/api/v1/hr/leave", headers=headers(), json=data).status_code == 409
    login(HR)
    assert (
        client.put(
            endpoint + "2027", headers=headers(), json={"allowance_days": 1, "counting": "calendar"}
        ).status_code
        == 200
    )
    assert client.get(endpoint + "2027", headers=headers(ORG_B)).status_code == 404
    login(DEV)
    assert client.post("/api/v1/hr/leave", headers=headers(), json=data).status_code == 201


def test_hr_cannot_set_own_allowance(client, db):
    record = employee(db, user=HR)
    login(HR)
    assert (
        client.put(
            f"/api/v1/hr/employees/{record.id}/leave-allowance/2026",
            headers=headers(),
            json={"allowance_days": 30},
        ).status_code
        == 403
    )


def test_incident_notes_are_analyst_scoped_and_not_owner_visible(client, db):
    incident = Incident(
        id=identifier(),
        organization_id=ORG_A,
        actor_id=DEV,
        fingerprint="a" * 64,
        event_ids=[],
        risk=10,
        explanation="Fixture",
        synthetic=True,
    )
    db.add(incident)
    db.commit()
    endpoint = f"/api/v1/vader/incidents/{incident.id}/notes"
    login(ANALYST)
    response = client.post(
        endpoint,
        headers=headers(),
        json={"body": "Investigated synthetic event", "reference": "case-123"},
    )
    assert response.status_code == 201, response.text
    assert response.json()["author_id"] == ANALYST
    assert len(client.get(endpoint, headers=headers()).json()) == 1
    assert client.get(endpoint, headers=headers(ORG_B)).status_code == 404
    login(OWNER)
    assert client.get(endpoint, headers=headers()).status_code == 403
