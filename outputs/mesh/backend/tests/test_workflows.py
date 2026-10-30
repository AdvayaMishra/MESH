from app.models import AuditLog, Delivery, Incident, Membership, Outbox, SecurityEvent, identifier
from app.worker import consume
from conftest import ANALYST, ANALYST2, DEV, ORG_A, ORG_B, OWNER, headers, login
from sqlalchemy import select


def test_project_approval_transition(client, db):
    login(DEV)
    created = client.post(
        "/api/v1/projects", headers=headers(), json={"name": "Project", "description": "Proposal"}
    )
    assert created.status_code == 201, created.text
    pid = created.json()["id"]
    assert (
        client.post(
            f"/api/v1/projects/{pid}/decision", headers=headers(), json={"decision": "approved"}
        ).status_code
        == 403
    )
    login(OWNER)
    assert (
        client.post(
            f"/api/v1/projects/{pid}/decision", headers=headers(), json={"decision": "approved"}
        ).status_code
        == 409
    )
    reviewer = identifier()
    db.add(
        Membership(
            organization_id=ORG_A,
            user_id=reviewer,
            email=reviewer + "@example.org",
            role="senior_developer",
        )
    )
    db.commit()
    login(reviewer)
    assert (
        client.post(
            f"/api/v1/projects/{pid}/decision", headers=headers(), json={"decision": "reviewed"}
        ).status_code
        == 200
    )
    login(OWNER)
    assert (
        client.post(
            f"/api/v1/projects/{pid}/decision", headers=headers(), json={"decision": "approved"}
        ).status_code
        == 200
    )
    assert (
        client.post(
            f"/api/v1/projects/{pid}/decision", headers=headers(), json={"decision": "approved"}
        ).status_code
        == 409
    )


def test_simulation_correlation_approval_and_tenant_isolation(client, db):
    login(ANALYST)
    run = identifier()
    response = client.post(f"/api/v1/vader/simulator/{run}", headers=headers())
    assert response.status_code == 200, response.text
    incident_id = response.json()[-1]["incident_id"]
    incident = db.get(Incident, incident_id)
    assert incident.synthetic and incident.risk == 85
    assert len(incident.event_ids) == 3
    assert client.post(f"/api/v1/vader/simulator/{run}", headers=headers()).json()[0]["duplicate"]
    assert len(db.scalars(select(SecurityEvent)).all()) == 3
    assert client.get("/api/v1/vader/incidents", headers=headers(ORG_B)).json() == []
    graph = client.get(f"/api/v1/vader/incidents/{incident_id}/graph", headers=headers()).json()
    assert len(graph["nodes"]) == 3 and len(graph["edges"]) == 2
    proposal = client.post(
        "/api/v1/vader/responses",
        headers=headers(),
        json={"incident_id": incident_id, "action": "revoke_session"},
    )
    assert proposal.status_code == 201, proposal.text
    rid = proposal.json()["id"]
    assert (
        client.post(f"/api/v1/vader/responses/{rid}/approve", headers=headers()).status_code == 403
    )
    login(ANALYST2)
    approved = client.post(f"/api/v1/vader/responses/{rid}/approve", headers=headers())
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "simulated"
    assert approved.json()["mode"] == "simulation"
    assert (
        client.post(f"/api/v1/vader/responses/{rid}/approve", headers=headers()).status_code == 409
    )


def test_outbox_idempotency_and_tenant_scope(db):
    db.add_all([Outbox(organization_id=org, topic="test", payload={}) for org in (ORG_A, ORG_B)])
    db.commit()
    assert consume(db, ORG_A) == 1
    db.commit()
    assert consume(db, ORG_A) == 0
    assert len(db.scalars(select(Delivery)).all()) == 1
    remaining = db.scalar(select(Outbox).where(Outbox.organization_id == ORG_B))
    assert remaining.status == "pending"


def test_failed_mail_rolls_back_invitation(client, db):
    from app.models import Invitation

    response = client.post(
        "/api/v1/invitations", headers=headers(), json={"email": "new@example.org", "role": "hr"}
    )
    assert response.status_code == 503
    assert db.scalars(select(Invitation)).all() == []
    assert db.scalars(select(AuditLog)).all() == []
