import pytest
from app.auth import Principal, principal
from app.main import app
from app.models import AuditLog, Membership, identifier
from conftest import ANALYST, ORG_A, ORG_B, headers, login
from sqlalchemy import select


def scenario(client):
    login(ANALYST)
    response = client.post("/api/v1/vader/simulator/" + identifier(), headers=headers())
    assert response.status_code == 200, response.text
    return response.json()[-1]


def test_sensitive_vader_reads_append_scoped_audits_and_expose_policy_provenance(client, db):
    result = scenario(client)
    incident = result["incident_id"]
    for path in (
        "/vader/anomalies",
        "/vader/incidents",
        f"/vader/incidents/{incident}",
        f"/vader/incidents/{incident}/graph",
    ):
        response = client.get("/api/v1" + path, headers=headers())
        assert response.status_code == 200, response.text
    assert response.json()["correlation_snapshot"]["policy_version"] == 0
    actions = set(db.scalars(select(AuditLog.action).where(AuditLog.organization_id == ORG_A)))
    assert {
        "security.anomalies.read",
        "security.incidents.read",
        "security.incident.read",
        "security.incident.graph.read",
    } <= actions
    for suffix in ("", "/graph"):
        assert (
            client.get(
                f"/api/v1/vader/incidents/{incident}{suffix}", headers=headers(ORG_B)
            ).status_code
            == 404
        )


@pytest.mark.parametrize(
    "kind",
    ["events", "event", "anomalies", "incidents", "incident", "graph", "policy", "policy_history"],
)
def test_sensitive_reads_recheck_revoked_role_after_cached_principal(client, db, kind):
    result = scenario(client)
    paths = {
        "events": "/vader/events",
        "event": "/vader/events/" + result["event_id"],
        "anomalies": "/vader/anomalies",
        "incidents": "/vader/incidents",
        "incident": "/vader/incidents/" + result["incident_id"],
        "graph": "/vader/incidents/" + result["incident_id"] + "/graph",
        "policy": "/vader/correlation-policy",
        "policy_history": "/vader/correlation-policies",
    }
    stale = Principal(ANALYST, ORG_A, "security_analyst")
    db.get(Membership, (ORG_A, ANALYST)).role = "junior_developer"
    db.commit()
    app.dependency_overrides[principal] = lambda: stale
    try:
        assert client.get("/api/v1" + paths[kind], headers=headers()).status_code == 403
    finally:
        app.dependency_overrides.pop(principal)
