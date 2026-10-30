from app.models import Employee, Finding, Incident, Outbox, Repository, identifier
from conftest import ANALYST, DEV, HR, ORG_A, ORG_B, OWNER, headers, login


def test_employee_search_escapes_wildcards_and_sorts_only_inside_the_tenant(client, db):
    db.add_all(
        [
            Employee(organization_id=ORG_A, user_id=DEV, name="Alice%", department="Engineering"),
            Employee(organization_id=ORG_A, user_id=OWNER, name="Zed", department="Finance"),
            Employee(
                organization_id=ORG_B, user_id=DEV, name="Alice% foreign", department="Engineering"
            ),
        ]
    )
    db.commit()
    login(HR)
    response = client.get(
        "/api/v1/employees?search=%25&sort_by=name&direction=desc", headers=headers()
    )
    assert response.status_code == 200, response.text
    assert [record["name"] for record in response.json()] == ["Alice%"]
    records = client.get("/api/v1/employees?department=Engineering", headers=headers()).json()
    assert len(records) == 1 and records[0]["name"] == "Alice%"
    assert client.get("/api/v1/employees?sort_by=password", headers=headers()).status_code == 422


def test_findings_collection_filters_severity_numerically_and_enforces_repository_scope(client, db):
    repository = Repository(
        id=identifier(), organization_id=ORG_A, full_name="org/repo", installation_id=1
    )
    db.add(repository)
    db.flush()
    for severity in ("info", "critical", "high"):
        db.add(
            Finding(
                organization_id=ORG_A,
                repository_id=repository.id,
                scanner="bandit",
                rule_id="fixture",
                severity=severity,
                file_path="fixture.py",
                line=1,
            )
        )
    db.commit()
    login(ANALYST)
    endpoint = f"/api/v1/repositories/{repository.id}/findings"
    response = client.get(endpoint + "?sort_by=severity&direction=desc", headers=headers())
    assert response.status_code == 200, response.text
    assert [row["severity"] for row in response.json()] == ["critical", "high", "info"]
    assert (
        len(client.get(endpoint + "?severity=high&scanner=bandit", headers=headers()).json()) == 1
    )
    assert client.get(endpoint, headers=headers(ORG_B)).status_code == 404
    login(OWNER)
    assert client.get(endpoint, headers=headers()).status_code == 403


def test_incident_filters_keep_simulated_results_separate_and_tenant_scoped(client, db):
    for org, synthetic, risk in ((ORG_A, True, 90), (ORG_A, False, 20), (ORG_B, False, 99)):
        db.add(
            Incident(
                organization_id=org,
                actor_id=DEV,
                fingerprint=identifier(),
                event_ids=[],
                risk=risk,
                synthetic=synthetic,
                explanation="Fixture",
            )
        )
    db.commit()
    login(ANALYST)
    endpoint = "/api/v1/vader/incidents"
    assert [
        row["risk"] for row in client.get(endpoint + "?synthetic=false", headers=headers()).json()
    ] == [20]
    assert [
        row["risk"] for row in client.get(endpoint + "?minimum_risk=80", headers=headers()).json()
    ] == [90]
    assert client.get(endpoint + "?minimum_risk=101", headers=headers()).status_code == 422


def test_typed_job_views_never_serialize_credentials_or_payloads(client, db):
    item = Outbox(
        id=identifier(),
        organization_id=ORG_A,
        topic="mail.invitation",
        payload={"ciphertext": "PRIVATE"},
    )
    db.add(item)
    db.commit()
    response = client.get("/api/v1/jobs?topic=mail.invitation&status=pending", headers=headers())
    assert response.status_code == 200, response.text
    assert response.json()[0]["id"] == item.id and "PRIVATE" not in response.text
    detail = client.get("/api/v1/jobs/" + item.id, headers=headers())
    assert "payload" not in detail.json() and "available_at" in detail.json()
    assert client.get("/api/v1/jobs/" + item.id, headers=headers(ORG_B)).status_code == 404


def test_financial_months_must_represent_real_calendar_months(client):
    response = client.post(
        "/api/v1/finance/costs",
        headers=headers(),
        json={
            "request_key": identifier(),
            "period": "0000-01",
            "department": "Engineering",
            "category": "cloud",
            "currency": "INR",
            "amount": "10.00",
        },
    )
    assert response.status_code == 422
