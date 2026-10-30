from datetime import timedelta

import pytest
from app.models import (
    Anomaly,
    CloudAssessment,
    Finding,
    Repository,
    RiskAssessment,
    SecurityEvent,
    identifier,
    now,
)
from app.risk_engine import DEFAULT_THRESHOLDS, DEFAULT_WEIGHTS, DIMENSIONS, calculate
from conftest import ANALYST, ANALYST2, DEV, HR, ORG_A, ORG_B, OWNER, headers, login


def policy(client, organization=ORG_A, weights=None):
    login(OWNER)
    response = client.post(
        "/api/v1/vader/risk-policies",
        headers=headers(organization),
        json={"weights": weights or DEFAULT_WEIGHTS},
    )
    assert response.status_code == 201, response.text
    return response.json()


def assessment(client, **values):
    login(ANALYST)
    return client.post(
        "/api/v1/vader/risk-assessments",
        headers=headers(),
        json={"request_key": identifier(), **values},
    )


@pytest.mark.parametrize(
    "value,classification",
    [(0, "low"), (25, "medium"), (50, "high"), (75, "critical"), (100, "critical")],
)
def test_weighted_risk_boundaries_and_full_coverage(value, classification):
    result = calculate(dict.fromkeys(DIMENSIONS, value), DEFAULT_WEIGHTS, DEFAULT_THRESHOLDS)
    assert result["overall_score"] == value and result["classification"] == classification
    assert result["coverage_weight"] == 100 and result["partial"] is False
    assert (
        result["missing_dimension_lower_bound"] == result["missing_dimension_upper_bound"] == value
    )
    assert result["calibrated_probability"] is False


def test_unknown_dimensions_are_not_zero_and_bounds_are_explicit():
    scores = dict.fromkeys(DIMENSIONS)
    unknown = calculate(scores, DEFAULT_WEIGHTS, DEFAULT_THRESHOLDS)
    assert unknown["overall_score"] is None and unknown["classification"] == "unassessed"
    assert unknown["missing_dimension_upper_bound"] == 100
    scores["identity"] = 80
    result = calculate(scores, DEFAULT_WEIGHTS, DEFAULT_THRESHOLDS)
    assert result["overall_score"] == 80 and result["coverage_weight"] == 15
    assert (
        result["missing_dimension_lower_bound"] == 12
        and result["missing_dimension_upper_bound"] == 97
    )
    assert result["classification_provisional"] is True


@pytest.mark.parametrize(
    "weights",
    [
        dict.fromkeys(DIMENSIONS, 1),
        {**DEFAULT_WEIGHTS, "network": True},
        {**DEFAULT_WEIGHTS, "extra": 0},
        {**DEFAULT_WEIGHTS, "network": -1},
    ],
)
def test_invalid_weights_never_create_policy(client, weights):
    login(OWNER)
    assert (
        client.post(
            "/api/v1/vader/risk-policies", headers=headers(), json={"weights": weights}
        ).status_code
        == 422
    )


def test_policy_version_history_idempotency_and_roles(client, db):
    first = policy(client)
    key = identifier()
    response = assessment(client, request_key=key)
    assert response.status_code == 201, response.text
    created = response.json()
    assert created["result"]["overall_score"] is None
    second = policy(
        client,
        weights={dimension: 100 if dimension == "identity" else 0 for dimension in DIMENSIONS},
    )
    assert first["version"] == 1 and second["version"] == 2
    replay = assessment(client, request_key=key)
    assert replay.json()["id"] == created["id"] and replay.json()["policy_id"] == first["id"]
    assert assessment(client, request_key=key, window_hours=1).status_code == 409
    login(ANALYST2)
    assert (
        client.post(
            "/api/v1/vader/risk-assessments", headers=headers(), json={"request_key": key}
        ).status_code
        == 409
    )
    login(OWNER)
    summary = client.get("/api/v1/vader/risk-summary", headers=headers()).json()
    assert summary["available"] and "components" not in summary
    assert (
        client.get("/api/v1/vader/risk-assessments/" + created["id"], headers=headers()).status_code
        == 403
    )
    login(HR)
    assert client.get("/api/v1/vader/risk-policies", headers=headers()).status_code == 403
    login(ANALYST)
    assert client.post("/api/v1/vader/risk-policies", headers=headers(), json={}).status_code == 403
    assert (
        client.get(
            "/api/v1/vader/risk-assessments/" + created["id"], headers=headers(ORG_B)
        ).status_code
        == 404
    )
    assert client.get("/api/v1/vader/risk-assessments", headers=headers(ORG_B)).json() == []
    assert db.get(RiskAssessment, created["id"]).result["policy_version"] == 1


def event(db, category, organization=ORG_A, synthetic=False, occurred_at=None):
    record = SecurityEvent(
        id=identifier(),
        organization_id=organization,
        source_id=identifier(),
        occurred_at=occurred_at or now(),
        actor_id=DEV,
        category=category,
        action="fixture",
        result="success",
        count=1,
        synthetic=synthetic,
    )
    db.add(record)
    db.flush()
    return record


def test_event_deduplication_time_tenant_and_synthetic_separation(client, db):
    policy(client)
    source = event(db, "api")
    excluded = [
        event(db, "network", organization=ORG_B),
        event(db, "network", synthetic=True),
        event(db, "network", occurred_at=now() - timedelta(days=10)),
        event(db, "network", occurred_at=now() + timedelta(minutes=2)),
    ]
    for rule, weight in [("api_volume", 20), ("volume_zscore", 15)]:
        db.add(
            Anomaly(
                organization_id=ORG_A,
                event_id=source.id,
                rule=rule,
                weight=weight,
                explanation="Fixture",
            )
        )
    db.commit()
    response = assessment(client)
    assert response.status_code == 201, response.text
    result = response.json()["result"]
    assert result["components"]["behavior"]["score"] == 40
    assert result["components"]["behavior"]["evidence_ids"] == [source.id]
    assert result["components"]["api"]["score"] is None
    assert result["components"]["network"]["score"] is None
    assert all(record.id not in response.text for record in excluded)


def test_cloud_and_code_inputs_do_not_enter_synthetic_assessments(client, db):
    policy(client)
    repo = Repository(organization_id=ORG_A, full_name="fixture/risk", installation_id=1)
    db.add(repo)
    db.flush()
    db.add(
        Finding(
            organization_id=ORG_A,
            repository_id=repo.id,
            scanner="bandit",
            rule_id="fixture",
            severity="critical",
            file_path="fixture.py",
            line=1,
            created_at=now() - timedelta(days=60),
        )
    )
    db.add(
        CloudAssessment(
            organization_id=ORG_A,
            findings=[{"severity": "high"}],
            partial=False,
            errors=[],
            coverage=[],
            limitations=[],
        )
    )
    db.commit()
    normal = assessment(client).json()["result"]["components"]
    assert normal["code_security"]["score"] == 100 and normal["cloud_posture"]["score"] == 75
    synthetic = assessment(client, synthetic=True).json()["result"]["components"]
    assert (
        synthetic["code_security"]["score"] is None and synthetic["cloud_posture"]["score"] is None
    )


def test_policy_required_and_foreign_policy_is_not_usable(client):
    assert assessment(client).status_code == 409
    foreign = policy(client, organization=ORG_B)
    assert assessment(client, policy_id=foreign["id"]).status_code == 404


def test_risk_ai_uses_only_authorized_aggregate_context(client):
    policy(client)
    record = assessment(client).json()
    login(ANALYST)
    endpoint = "/api/v1/ai/risk-assessments/" + record["id"]
    response = client.get(endpoint, headers=headers())
    assert response.status_code == 200, response.text
    assert response.json()["provider"] == "local-deterministic"
    assert "coverage_weight=0" in response.json()["summary"]
    assert "evidence_ids" not in response.text
    assert client.get(endpoint, headers=headers(ORG_B)).status_code == 404
    login(OWNER)
    assert client.get(endpoint, headers=headers()).status_code == 403


def test_history_deltas_require_same_policy_window_and_observed_dimensions(client, db):
    policy(client)
    first_event = event(db, "authentication")
    db.add(
        Anomaly(
            organization_id=ORG_A,
            event_id=first_event.id,
            rule="fixture",
            weight=20,
            explanation="Fixture",
        )
    )
    db.commit()
    first = assessment(client).json()
    second_event = event(db, "authentication")
    db.add(
        Anomaly(
            organization_id=ORG_A,
            event_id=second_event.id,
            rule="fixture",
            weight=30,
            explanation="Fixture",
        )
    )
    db.commit()
    second = assessment(client).json()
    comparison = second["result"]["comparison"]
    assert comparison == {
        "previous_assessment_id": first["id"],
        "comparable": True,
        "score_delta": 20.0,
    }
    changed_window = assessment(client, window_hours=1).json()["result"]["comparison"]
    assert changed_window["comparable"] is False and changed_window["score_delta"] is None
    login(ANALYST)
    history = client.get("/api/v1/vader/risk-assessments", headers=headers()).json()
    assert len(history) == 3 and history[0]["result"]["window_hours"] == 1


@pytest.mark.parametrize("category,weight", [("network", 20), ("behavior", 15)])
def test_new_signal_categories_are_ingested_and_detected(client, db, category, weight):
    policy(client)
    login(ANALYST)
    response = client.post(
        "/api/v1/vader/events",
        headers=headers(),
        json={
            "source_id": identifier(),
            "occurred_at": now().isoformat(),
            "actor_id": DEV,
            "category": category,
            "action": "fixture",
            "result": "success",
            "count": 101,
        },
    )
    assert response.status_code == 201, response.text
    result = assessment(client).json()["result"]["components"]
    assert result[category]["score"] == weight * 2
