from app.models import Anomaly, Incident, IncidentEvent, SecurityEvent, identifier, now
from conftest import ANALYST, DEV, ORG_A, ORG_B, OWNER, headers, login


def seed(db, org, category, synthetic=False):
    event = SecurityEvent(
        organization_id=org,
        source_id=identifier(),
        occurred_at=now(),
        actor_id=DEV,
        category=category,
        action="fixture",
        result="success",
        synthetic=synthetic,
    )
    db.add(event)
    db.flush()
    return event


def test_retained_risk_projection_deduplicates_rules_links_and_keeps_stored_score(client, db):
    first, second = seed(db, ORG_A, "privilege"), seed(db, ORG_A, "download")
    incident = Incident(
        organization_id=ORG_A,
        actor_id=DEV,
        fingerprint=identifier(),
        event_ids=[first.id, second.id, first.id],
        risk=99,
        explanation="Fixture",
        synthetic=False,
    )
    db.add(incident)
    db.flush()
    db.add(IncidentEvent(organization_id=ORG_A, incident_id=incident.id, event_id=first.id))
    for event, weight in [(first, 15), (first, 30), (second, 20)]:
        db.add(
            Anomaly(
                organization_id=ORG_A,
                event_id=event.id,
                rule=identifier(),
                weight=weight,
                explanation="Fixture",
            )
        )
    db.commit()
    login(ANALYST)
    endpoint = f"/api/v1/vader/incidents/{incident.id}/risk-evidence"
    response = client.get(endpoint, headers=headers())
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["stored_score"] == 99 and result["retained_evidence_score"] == 50
    assert result["matches_stored_score"] is False and result["evidence_complete"] is True
    assert (
        result["original_model_version"] is None
        and result["projection_version"] == "retained-event-weights-v1"
    )
    assert result["dimensions"] == [
        {"category": "download", "event_count": 1, "scored_events": 1, "raw_weight": 20},
        {"category": "privilege", "event_count": 1, "scored_events": 1, "raw_weight": 30},
    ]
    assert db.get(Incident, incident.id).risk == 99
    assert client.get(endpoint, headers=headers(ORG_B)).status_code == 404
    login(OWNER)
    assert client.get(endpoint, headers=headers()).status_code == 403


def test_projection_marks_foreign_missing_and_wrong_provenance_evidence_incomplete(client, db):
    foreign = seed(db, ORG_B, "cloud")
    synthetic = seed(db, ORG_A, "cloud", synthetic=True)
    unscored = seed(db, ORG_A, "api")
    incident = Incident(
        organization_id=ORG_A,
        actor_id=DEV,
        fingerprint=identifier(),
        event_ids=[foreign.id, synthetic.id, unscored.id, identifier()],
        risk=0,
        explanation="Fixture",
        synthetic=False,
    )
    db.add(incident)
    db.commit()
    login(ANALYST)
    response = client.get(f"/api/v1/vader/incidents/{incident.id}/risk-evidence", headers=headers())
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["evidence_complete"] is False and data["missing_events"] == 3
    assert data["dimensions"] == [
        {"category": "api", "event_count": 1, "scored_events": 0, "raw_weight": 0}
    ]
    assert foreign.id not in response.text and synthetic.id not in response.text


def test_projection_caps_score_and_handles_empty_legacy_evidence(client, db):
    event = seed(db, ORG_A, "download")
    incident = Incident(
        organization_id=ORG_A,
        actor_id=DEV,
        fingerprint=identifier(),
        event_ids=[],
        risk=100,
        explanation="Fixture",
        synthetic=False,
    )
    db.add(incident)
    db.flush()
    db.add(IncidentEvent(organization_id=ORG_A, incident_id=incident.id, event_id=event.id))
    db.add(
        Anomaly(
            organization_id=ORG_A,
            event_id=event.id,
            rule="fixture",
            weight=150,
            explanation="Fixture",
        )
    )
    db.commit()
    login(ANALYST)
    result = client.get(
        f"/api/v1/vader/incidents/{incident.id}/risk-evidence", headers=headers()
    ).json()
    assert result["retained_evidence_score"] == 100 and result["matches_stored_score"] is True
    assert result["dimensions"][0]["raw_weight"] == 150
