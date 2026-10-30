from datetime import timedelta, timezone

import pytest
from app.auth import Principal
from app.models import Anomaly, SecurityEvent, now
from app.schemas import EventInput
from app.vader import ingest
from conftest import ANALYST, DEV, ORG_A, ORG_B, headers, login
from fastapi import HTTPException
from sqlalchemy import func, select


def event():
    return {
        "source_id": "immutable-receipt",
        "occurred_at": (now() - timedelta(minutes=1)).isoformat(),
        "actor_id": DEV,
        "category": "api",
        "action": "request",
        "result": "success",
        "count": 2000,
    }


@pytest.mark.parametrize(
    "change",
    [
        {"actor_id": "different"},
        {"category": "download"},
        {"count": 1},
        {"result": "failure"},
        {"action": "different"},
        {"session_id": "new-session"},
        {"resource_id": "new-resource"},
        {"occurred_at": (now() - timedelta(minutes=2)).isoformat()},
    ],
)
def test_changed_telemetry_receipt_is_rejected_without_new_evidence(client, db, change):
    login(ANALYST)
    payload = event()
    first = client.post("/api/v1/vader/events", headers=headers(), json=payload)
    assert first.status_code == 201, first.text
    replay = client.post("/api/v1/vader/events", headers=headers(), json=payload | change)
    assert replay.status_code == 409, replay.text
    assert db.scalar(select(func.count()).select_from(SecurityEvent)) == 1
    assert db.scalar(select(func.count()).select_from(Anomaly)) == 1


def test_identical_receipt_and_equivalent_timezone_are_idempotent_and_tenant_scoped(client, db):
    login(ANALYST)
    payload = event()
    first = client.post("/api/v1/vader/events", headers=headers(), json=payload).json()
    data = EventInput.model_validate(payload)
    payload["occurred_at"] = data.occurred_at.astimezone(
        timezone(timedelta(hours=5, minutes=30))
    ).isoformat()
    replay = client.post("/api/v1/vader/events", headers=headers(), json=payload)
    assert replay.status_code == 201, replay.text
    assert replay.json()["duplicate"] is True and replay.json()["event_id"] == first["event_id"]
    other = client.post("/api/v1/vader/events", headers=headers(ORG_B), json=payload)
    assert other.status_code == 201 and other.json()["duplicate"] is False


def test_real_event_cannot_reuse_simulation_receipt(db):
    data = EventInput.model_validate(event())
    p = Principal(ANALYST, ORG_A, "security_analyst")
    ingest(db, p, data, synthetic=True)
    with pytest.raises(HTTPException) as error:
        ingest(db, p, data, synthetic=False)
    assert error.value.status_code == 409


def test_baseline_cold_start_is_per_category_and_excludes_synthetic_and_other_tenants(client, db):
    timestamp = now() - timedelta(minutes=1)
    for org, category, count, synthetic in [
        (ORG_A, "api", 19, False),
        (ORG_A, "database", 20, False),
        (ORG_A, "api", 5, True),
        (ORG_B, "api", 20, False),
    ]:
        for index in range(count):
            db.add(
                SecurityEvent(
                    organization_id=org,
                    source_id=f"{org}:{category}:{synthetic}:{index}",
                    occurred_at=timestamp,
                    actor_id=DEV,
                    category=category,
                    action="request",
                    result="success",
                    count=1,
                    synthetic=synthetic,
                )
            )
    db.commit()
    login(ANALYST)
    endpoint = f"/api/v1/vader/baseline/{DEV}"
    api = client.get(endpoint, headers=headers()).json()
    assert api["category"] == "api" and api["observations"] == 19 and api["cold_start"] is True
    database = client.get(endpoint + "?category=database", headers=headers()).json()
    assert database["observations"] == 20 and database["cold_start"] is False
    assert client.get(endpoint + "?category=authentication", headers=headers()).status_code == 422
