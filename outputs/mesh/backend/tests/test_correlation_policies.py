from datetime import timedelta

import pytest
from app.auth import Principal
from app.correlation import CorrelationConfig, PolicyChange, create_policy
from app.models import (
    Anomaly,
    AuditLog,
    CorrelationPolicy,
    Incident,
    Membership,
    SecurityEvent,
    identifier,
    now,
)
from app.schemas import EventInput
from app.vader import ingest
from conftest import ANALYST, DEV, HR, ORG_A, ORG_B, OWNER, headers, login
from fastapi import HTTPException
from sqlalchemy import select


@pytest.fixture(autouse=True)
def analyst(client):
    login(ANALYST)


def policy(client, expected=0, **configuration):
    response = client.put(
        "/api/v1/vader/correlation-policy",
        headers=headers(),
        json={"expected_version": expected, "configuration": configuration},
    )
    assert response.status_code == 200, response.text
    return response.json()


def event(client, category, *, minute=0, **fields):
    failure = category == "authentication"
    payload = {
        "source_id": identifier(),
        "actor_id": DEV,
        "category": category,
        "action": "reported",
        "result": "failure" if failure else "success",
        "count": 2000,
        "occurred_at": (now() - timedelta(minutes=10) + timedelta(minutes=minute)).isoformat(),
        **fields,
    }
    response = client.post("/api/v1/vader/events", headers=headers(), json=payload)
    assert response.status_code == 201, response.text
    return response.json(), payload


def test_default_policy_versions_history_and_concurrent_edit_guard(client):
    default = client.get("/api/v1/vader/correlation-policy", headers=headers()).json()
    assert default["id"] is None and default["version"] == 0
    assert default["configuration"]["window_minutes"] == 30
    first = policy(client, window_minutes=15)
    assert first["version"] == 1 and first["created_by"] == ANALYST
    assert (
        client.put(
            "/api/v1/vader/correlation-policy",
            headers=headers(),
            json={"expected_version": 0, "configuration": {}},
        ).status_code
        == 409
    )
    second = policy(client, 1, link_mode="resource")
    history = client.get("/api/v1/vader/correlation-policies", headers=headers()).json()
    assert [row["id"] for row in history["policies"]] == [second["id"], first["id"]]
    empty = client.get("/api/v1/vader/correlation-policies?offset=99", headers=headers()).json()
    assert empty["policies"] == [] and empty["total_policies"] == 2
    assert (
        client.get("/api/v1/vader/correlation-policy", headers=headers(ORG_B)).json()["version"]
        == 0
    )


@pytest.mark.parametrize(
    "configuration",
    [
        {"window_minutes": 0},
        {"window_minutes": 1441},
        {"window_minutes": True},
        {"minimum_categories": 1},
        {"minimum_categories": 4},
        {"minimum_events": 5001},
        {"evidence_limit": 2},
        {"enabled": "false"},
        {"categories": ["api", "api", "download"]},
        {"categories": ["api", "download"]},
        {"link_mode": "untrusted"},
        {"organization_id": ORG_B},
    ],
)
def test_invalid_or_unbounded_correlation_configuration_is_rejected(client, configuration):
    assert (
        client.put(
            "/api/v1/vader/correlation-policy",
            headers=headers(),
            json={"expected_version": 0, "configuration": configuration},
        ).status_code
        == 422
    )


@pytest.mark.parametrize("user", [OWNER, HR, DEV])
def test_policy_read_and_write_require_security_authority(client, user):
    login(user)
    assert client.get("/api/v1/vader/correlation-policy", headers=headers()).status_code == 403
    assert (
        client.put(
            "/api/v1/vader/correlation-policy",
            headers=headers(),
            json={"expected_version": 0, "configuration": {}},
        ).status_code
        == 403
    )


def test_policy_write_and_ingestion_refresh_stale_authority(db):
    stale = Principal(ANALYST, ORG_A, "security_analyst")
    db.get(Membership, (ORG_A, ANALYST)).role = "junior_developer"
    db.commit()
    with pytest.raises(HTTPException) as error:
        create_policy(
            db, stale, PolicyChange(expected_version=0, configuration=CorrelationConfig())
        )
    assert error.value.status_code == 403
    with pytest.raises(HTTPException) as error:
        ingest(
            db,
            stale,
            EventInput(
                source_id="stale",
                actor_id=DEV,
                category="api",
                action="request",
                result="success",
                count=2000,
                occurred_at=now(),
            ),
        )
    assert error.value.status_code == 403
    assert db.query(CorrelationPolicy).count() == 0 and db.query(SecurityEvent).count() == 0


def test_policy_change_does_not_rewrite_or_merge_previous_incident_provenance(client, db):
    for category in ("authentication", "privilege", "download"):
        result, _ = event(client, category)
    original = db.get(Incident, result["incident_id"])
    assert original.correlation_policy_id is None
    assert original.correlation_snapshot["policy_version"] == 0
    original_ids, original_snapshot, original_risk = (
        list(original.event_ids),
        dict(original.correlation_snapshot),
        original.risk,
    )
    configured = policy(client)
    later, payload = event(client, "api")
    assert later["incident_id"] != original.id and later["correlation_status"] == "matched"
    db.refresh(original)
    assert (
        original.event_ids == original_ids
        and original.correlation_snapshot == original_snapshot
        and original.risk == original_risk
    )
    current = db.get(Incident, later["incident_id"])
    assert current.correlation_policy_id == configured["id"]
    assert current.correlation_snapshot["policy_version"] == 1
    replay = client.post("/api/v1/vader/events", headers=headers(), json=payload).json()
    assert replay["duplicate"] and replay["correlation_status"] == "not_recomputed"


@pytest.mark.parametrize(
    "mode,fields",
    [
        ("actor", {}),
        ("session", {"session_id": "same"}),
        ("resource", {"resource_id": "same"}),
        ("session_or_resource", {"resource_id": "same"}),
    ],
)
def test_configured_relationship_and_category_thresholds(client, mode, fields):
    policy(client, link_mode=mode, minimum_categories=2, minimum_events=2)
    event(client, "authentication", **fields)
    matched, _ = event(client, "download", **fields)
    assert matched["correlation_status"] == "matched" and matched["incident_id"]


@pytest.mark.parametrize("mode", ["session", "resource", "session_or_resource"])
def test_missing_relationship_values_never_match_each_other(client, mode):
    policy(client, link_mode=mode, minimum_categories=2, minimum_events=2)
    event(client, "authentication")
    last, _ = event(client, "download")
    assert last["correlation_status"] == "insufficient" and last["incident_id"] is None


def test_time_window_and_disabled_policy_preserve_ingestion_and_anomalies(client, db):
    policy(client, window_minutes=1, minimum_categories=2, minimum_events=2)
    event(client, "authentication", minute=0)
    result, _ = event(client, "download", minute=3)
    assert result["correlation_status"] == "insufficient"
    policy(client, 1, enabled=False)
    disabled, _ = event(client, "privilege", minute=4)
    assert disabled["correlation_status"] == "disabled"
    assert db.query(Anomaly).count() == 3 and db.query(SecurityEvent).count() == 3


def test_excluded_categories_and_evidence_overflow_are_explicit_not_clean(client, db):
    policy(client, categories=["authentication", "privilege", "download"], evidence_limit=3)
    excluded, _ = event(client, "api")
    assert excluded["correlation_status"] == "excluded"
    for category in ("authentication", "privilege", "download"):
        matched, _ = event(client, category)
    assert matched["correlation_status"] == "matched"
    incomplete, _ = event(client, "download")
    assert incomplete["correlation_status"] == "incomplete" and incomplete["incident_id"] is None
    assert (
        db.scalar(select(AuditLog.id).where(AuditLog.action == "security.correlation.incomplete"))
        is not None
    )
    assert db.query(SecurityEvent).count() == 5


def test_multiple_rules_on_one_event_do_not_consume_multiple_evidence_slots(client, db):
    policy(client, evidence_limit=3)
    first, _ = event(client, "authentication")
    db.add(
        Anomaly(
            organization_id=ORG_A,
            event_id=first["event_id"],
            rule="synthetic-extra",
            weight=1,
            explanation="Fixture",
        )
    )
    db.commit()
    event(client, "privilege")
    last, _ = event(client, "download")
    assert last["correlation_status"] == "matched"
    assert db.get(Incident, last["incident_id"]).risk == 85


@pytest.mark.parametrize("mode,field", [("session", "session_id"), ("resource", "resource_id")])
def test_different_relationships_are_not_merged(client, mode, field):
    policy(client, link_mode=mode, minimum_categories=2, minimum_events=2)
    event(client, "authentication", **{field: "first"})
    result, _ = event(client, "download", **{field: "second"})
    assert result["correlation_status"] == "insufficient"


def test_minimum_event_threshold_is_independent_of_categories(client):
    policy(client, minimum_categories=2, minimum_events=4)
    for category in ("authentication", "download", "authentication"):
        result, _ = event(client, category)
        assert result["correlation_status"] == "insufficient"
    result, _ = event(client, "download")
    assert result["correlation_status"] == "matched"
