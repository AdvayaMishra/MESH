from app.models import Employee, IntegrationAccount, Membership, Project, identifier
from conftest import DEV, HR, ORG_A, ORG_B, OWNER, headers, login


def employee(db, org=ORG_A):
    record = Employee(
        id=identifier(),
        organization_id=org,
        user_id=DEV,
        name="Example",
        department="Engineering",
        status="active",
    )
    db.add(record)
    db.commit()
    return record


def test_leave_overlap_review_and_visibility(client, db):
    record = employee(db)
    login(DEV)
    data = {
        "employee_id": record.id,
        "starts_on": "2026-11-01",
        "ends_on": "2026-11-03",
        "reason": "Personal leave",
    }
    created = client.post("/api/v1/hr/leave", headers=headers(), json=data)
    assert created.status_code == 201, created.text
    assert client.post("/api/v1/hr/leave", headers=headers(), json=data).status_code == 409
    lid = created.json()["id"]
    assert (
        client.post(
            f"/api/v1/hr/leave/{lid}/decision", headers=headers(), json={"decision": "approved"}
        ).status_code
        == 403
    )
    login(HR)
    assert (
        client.post(
            f"/api/v1/hr/leave/{lid}/decision", headers=headers(), json={"decision": "approved"}
        ).status_code
        == 200
    )
    login(OWNER)
    assert client.get("/api/v1/hr/leave", headers=headers()).json() == []


def test_complaints_do_not_grant_owner_visibility(client):
    login(DEV)
    assert (
        client.post(
            "/api/v1/hr/complaints",
            headers=headers(),
            json={"subject": "Sensitive", "body": "Confidential employee report"},
        ).status_code
        == 201
    )
    login(OWNER)
    assert client.get("/api/v1/hr/complaints", headers=headers()).json() == []
    login(HR)
    assert len(client.get("/api/v1/hr/complaints", headers=headers()).json()) == 1
    assert client.get("/api/v1/hr/complaints", headers=headers(ORG_B)).json() == []


def test_offboarding_local_revocation_survives_external_pending(client, db):
    record = employee(db)
    db.add(
        IntegrationAccount(
            organization_id=ORG_A, user_id=DEV, provider="github", external_id="external-user"
        )
    )
    db.commit()
    login(HR)
    created = client.post(
        "/api/v1/hr/lifecycle",
        headers=headers(),
        json={"employee_id": record.id, "kind": "offboarding"},
    )
    assert created.status_code == 201, created.text
    plan = created.json()["id"]
    assert client.post(f"/api/v1/hr/lifecycle/{plan}/execute", headers=headers()).status_code == 409
    login(OWNER)
    assert (
        client.post(
            f"/api/v1/hr/lifecycle/{plan}/decision",
            headers=headers(),
            json={"decision": "approved"},
        ).status_code
        == 200
    )
    login(HR)
    result = client.post(f"/api/v1/hr/lifecycle/{plan}/execute", headers=headers())
    assert result.status_code == 200, result.text
    assert result.json()["status"] == "reconciliation_required"
    assert not db.get(Membership, (ORG_A, DEV)).active
    login(DEV)
    assert client.get("/api/v1/organizations/current", headers=headers()).status_code == 403


def test_finance_currency_isolation_forecast(client):
    for period, amount in [("2026-07", "100.10"), ("2026-08", "200.20"), ("2026-09", "300.30")]:
        response = client.post(
            "/api/v1/finance/costs",
            headers=headers(),
            json={
                "request_key": identifier(),
                "period": period,
                "department": "Engineering",
                "category": "cloud",
                "currency": "INR",
                "amount": amount,
            },
        )
        assert response.status_code == 201, response.text
    result = client.get("/api/v1/finance/summary", headers=headers()).json()
    assert result["total"] == "600.60" and result["forecast_next_month"] == "200.20"
    assert (
        client.get("/api/v1/finance/summary?currency=USD", headers=headers()).json()["total"] == "0"
    )
    assert client.get("/api/v1/finance/summary", headers=headers(ORG_B)).json()["total"] == "0"


def test_project_membership_and_task_transitions(client, db):
    senior = identifier()
    db.add(
        Membership(
            organization_id=ORG_A,
            user_id=senior,
            email=f"{senior}@example.org",
            role="senior_developer",
        )
    )
    project = Project(
        id=identifier(),
        organization_id=ORG_A,
        name="Approved",
        description="",
        proposer_id=DEV,
        status="approved",
    )
    db.add(project)
    db.commit()
    for user, manager in [(senior, True), (DEV, False)]:
        added = client.post(
            f"/api/v1/projects/{project.id}/members",
            headers=headers(),
            json={"user_id": user, "manager": manager},
        )
        assert added.status_code == 201, added.text
    login(senior)
    created = client.post(
        "/api/v1/tasks",
        headers=headers(),
        json={"project_id": project.id, "assignee_id": DEV, "title": "Build"},
    )
    assert created.status_code == 201, created.text
    task_id = created.json()["id"]
    login(DEV)
    for status in ("in_progress", "review"):
        response = client.patch(
            f"/api/v1/tasks/{task_id}", headers=headers(), json={"status": status}
        )
        assert response.status_code == 200, response.text
    assert (
        client.patch(
            f"/api/v1/tasks/{task_id}", headers=headers(), json={"status": "done"}
        ).status_code
        == 403
    )
    login(senior)
    assert (
        client.patch(
            f"/api/v1/tasks/{task_id}", headers=headers(), json={"status": "done"}
        ).status_code
        == 200
    )


def test_audit_chain_detects_mutation(client, db):
    from app.models import AuditLog
    from sqlalchemy import select

    client.get("/api/v1/finance/summary", headers=headers())
    valid = client.get("/api/v1/audit/integrity", headers=headers())
    assert valid.json()["valid"]
    row = db.scalar(select(AuditLog).where(AuditLog.organization_id == ORG_A))
    row.action = "tampered"
    db.commit()  # SQLite deliberately lacks PostgreSQL append-only triggers.
    assert not client.get("/api/v1/audit/integrity", headers=headers()).json()["valid"]
