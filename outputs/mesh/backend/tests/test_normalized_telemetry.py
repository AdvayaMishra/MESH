from datetime import timedelta

import pytest
from app.models import Anomaly, SecurityEvent, identifier, now
from conftest import ANALYST, DEV, ORG_B, OWNER, headers, login
from sqlalchemy import select


def payload(category="device", **kwargs):
    return {
        "source_id": identifier(),
        "occurred_at": now().isoformat(),
        "actor_id": DEV,
        "category": category,
        "action": "observed",
        "result": "success",
        "count": 1,
        **kwargs,
    }


def context():
    return {
        "source": {"kind": "device", "name": "fixture-collector", "version": "1.0"},
        "reported_severity": "critical",
        "ip": {
            "country_code": "IN",
            "asn": 64512,
            "address": {"value": "a" * 64, "method": "hmac-sha256", "key_id": "fixture-v1"},
        },
        "device": {
            "fingerprint": {"value": "b" * 64, "method": "hmac-sha256", "key_id": "fixture-v1"},
            "os_family": "linux",
            "new_device": True,
            "managed": False,
        },
    }


def test_typed_context_receipt_binding_filters_tenant_and_no_reported_severity_escalation(
    client, db
):
    login(ANALYST)
    body = payload(context=context())
    created = client.post("/api/v1/vader/events", headers=headers(), json=body)
    assert created.status_code == 201, created.text
    event_id = created.json()["event_id"]
    assert client.post("/api/v1/vader/events", headers=headers(), json=body).json()["duplicate"]
    stored = db.get(SecurityEvent, event_id)
    assert stored.context == context()
    anomaly = db.scalar(select(Anomaly).where(Anomaly.event_id == event_id))
    assert anomaly.rule == "new_device" and anomaly.weight == 15
    returned = client.get(f"/api/v1/vader/events/{event_id}", headers=headers()).json()
    assert returned["context"]["ip"]["address"]["method"] == "hmac-sha256"
    assert client.get(f"/api/v1/vader/events/{event_id}", headers=headers(ORG_B)).status_code == 404
    changed = {**body, "context": {**context(), "reported_severity": "low"}}
    assert client.post("/api/v1/vader/events", headers=headers(), json=changed).status_code == 409
    assert client.post("/api/v1/vader/events", headers=headers(ORG_B), json=body).status_code == 201
    listed = client.get(
        "/api/v1/vader/events?category=device&source_kind=device&reported_severity=critical",
        headers=headers(),
    )
    assert listed.status_code == 200 and [item["id"] for item in listed.json()] == [event_id]
    assert client.get("/api/v1/vader/events?source_kind=network", headers=headers()).json() == []
    login(OWNER)
    assert client.get(f"/api/v1/vader/events/{event_id}", headers=headers()).status_code == 403


@pytest.mark.parametrize(
    "extra",
    [
        {"ip": {"address": "192.0.2.10"}},
        {"ip": {"raw_ip": "192.0.2.10"}},
        {"device": {"user_agent": "PRIVATE"}},
        {"attributes": {"password": "PRIVATE"}},
        {"device": {"new_device": "true"}},
        {"attributes": {"bytes_transferred": True}},
        {"attributes": {"bytes_transferred": -1}},
        {"ip": {"asn": 0}},
        {"source": {"kind": "arbitrary", "name": "fixture"}},
        {"ip": {"address": {"value": "a" * 64, "method": "sha256", "key_id": "fixture"}}},
        {"source": {"kind": "manual", "name": "x" * 65}},
    ],
)
def test_metadata_never_accepts_raw_address_device_dump_arbitrary_logs_or_unbounded_values(
    client, extra
):
    login(ANALYST)
    response = client.post("/api/v1/vader/events", headers=headers(), json=payload(context=extra))
    assert response.status_code == 422
    assert "192.0.2.10" not in response.text and "PRIVATE" not in response.text


@pytest.mark.parametrize(
    "category,action,count,metadata,rule",
    [
        ("session", "revoked_session_used", 1, {}, "revoked_session_activity"),
        ("device", "observed", 1, {"device": {"new_device": True}}, "new_device"),
        (
            "file",
            "read",
            501,
            {"attributes": {"operation": "read", "data_classification": "restricted"}},
            "file_volume",
        ),
        ("repository", "branch_protection_disabled", 1, {}, "repository_activity"),
        (
            "cloud_audit",
            "root_login",
            1,
            {"attributes": {"cloud_service": "iam"}},
            "cloud_audit_activity",
        ),
    ],
)
def test_new_reported_sources_have_explainable_signals(
    client, db, category, action, count, metadata, rule
):
    login(ANALYST)
    response = client.post(
        "/api/v1/vader/events",
        headers=headers(),
        json=payload(category, action=action, count=count, context=metadata),
    )
    assert response.status_code == 201, response.text
    anomaly = db.scalar(select(Anomaly).where(Anomaly.event_id == response.json()["event_id"]))
    assert anomaly.rule == rule and "not proof" in anomaly.explanation


def test_metadata_defaults_preserve_legacy_receipts_and_none_is_canonical(client):
    login(ANALYST)
    body = payload("api")
    assert client.post("/api/v1/vader/events", headers=headers(), json=body).status_code == 201
    replay = client.post(
        "/api/v1/vader/events", headers=headers(), json={**body, "context": {"source": None}}
    )
    assert replay.status_code == 201 and replay.json()["duplicate"] is True
    assert (
        client.post(
            "/api/v1/vader/events", headers=headers(), json={**body, "resource_id": identifier()}
        ).status_code
        == 409
    )


def test_configurable_metadata_signals_and_file_statistical_cold_start(client, db):
    login(ANALYST)
    response = client.put(
        "/api/v1/vader/detection-policy",
        headers=headers(),
        json={"new_device": False, "revoked_session": False, "file": 10000},
    )
    assert response.status_code == 200
    body = payload(context={"device": {"new_device": True}})
    created = client.post("/api/v1/vader/events", headers=headers(), json=body)
    assert db.scalar(select(Anomaly).where(Anomaly.event_id == created.json()["event_id"])) is None
    timestamp = now() - timedelta(minutes=2)
    for index, count in enumerate([*range(1, 21), 1000]):
        created = client.post(
            "/api/v1/vader/events",
            headers=headers(),
            json=payload(
                "file", count=count, occurred_at=(timestamp + timedelta(seconds=index)).isoformat()
            ),
        )
        assert created.status_code == 201, created.text
    last = db.scalar(select(Anomaly).where(Anomaly.event_id == created.json()["event_id"]))
    assert last.rule == "volume_zscore"
    baseline = client.get(f"/api/v1/vader/baseline/{DEV}?category=file", headers=headers()).json()
    assert baseline["observations"] == 21 and baseline["cold_start"] is False


def test_reported_session_device_file_chain_maps_to_distinct_risk_dimensions(client):
    login(ANALYST)
    incident = None
    for body in [
        payload("session", action="revoked_session_used"),
        payload(context={"device": {"new_device": True}}),
        payload("file", count=501),
    ]:
        created = client.post("/api/v1/vader/events", headers=headers(), json=body)
        assert created.status_code == 201, created.text
        incident = created.json()["incident_id"] or incident
    assert incident is not None
    record = client.get("/api/v1/vader/incidents/" + incident, headers=headers()).json()
    assert record["risk"] == 60 and record["synthetic"] is False
