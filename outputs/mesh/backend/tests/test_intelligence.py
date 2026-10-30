import httpx
import pytest
from app.ai import HTTPProvider, generate
from app.auth import Principal
from app.cloud import AWSAssessment
from app.core.config import settings
from app.models import identifier
from conftest import ANALYST, ORG_A, ORG_B, OWNER, headers, login
from fastapi import HTTPException


def test_ai_rejects_raw_text_context(db):
    with pytest.raises(HTTPException):
        generate(db, Principal(OWNER, ORG_A, "owner"), "owner", {"employee_document": "PRIVATE"})


@pytest.mark.parametrize("provider", ["ollama", "gateway"])
def test_remote_models_require_explicit_external_authorization(monkeypatch, provider):
    monkeypatch.setattr(settings(), "ai_provider", provider)
    monkeypatch.setattr(settings(), "ai_url", "https://remote.example.org/generate")
    monkeypatch.setattr(settings(), "ai_allow_external", False)
    with pytest.raises(HTTPException):
        HTTPProvider().generate("owner", {"records": 1})


def test_ai_structured_adapter_rejects_bad_output(monkeypatch):
    monkeypatch.setattr(settings(), "ai_provider", "gateway")
    monkeypatch.setattr(settings(), "ai_allow_external", True)
    monkeypatch.setattr(settings(), "ai_url", "https://gateway.example.org/generate")
    with httpx.Client(
        transport=httpx.MockTransport(
            lambda _: httpx.Response(200, json={"output": {"summary": "No limitations"}})
        )
    ) as client:
        with pytest.raises(HTTPException):
            HTTPProvider(client).generate("owner", {"records": 1})


def test_ai_usage_and_authorization(client):
    login(OWNER)
    response = client.get("/api/v1/ai/owner", headers=headers())
    assert response.status_code == 200, response.text
    assert response.json()["provider"] == "local-deterministic"
    assert len(client.get("/api/v1/ai/usage", headers=headers()).json()) == 1
    assert client.get("/api/v1/ai/usage", headers=headers(ORG_B)).json() == []
    login(ANALYST)
    assert client.get("/api/v1/ai/owner", headers=headers()).status_code == 403


def test_aws_fixture_assessment_and_unknowns():
    class Client:
        def can_paginate(self, operation):
            return False

        def list_buckets(self):
            return {"Buckets": [{"Name": "fixture"}]}

        def get_bucket_policy_status(self, **kwargs):
            return {"PolicyStatus": {"IsPublic": True}}

        def get_bucket_encryption(self, **kwargs):
            raise RuntimeError("AccessDenied")

        def get_bucket_logging(self, **kwargs):
            return {}

        def describe_security_groups(self):
            return {
                "SecurityGroups": [
                    {
                        "GroupId": "sg-fixture",
                        "IpPermissions": [
                            {
                                "IpProtocol": "tcp",
                                "FromPort": 22,
                                "ToPort": 22,
                                "IpRanges": [{"CidrIp": "0.0.0.0/0"}],
                            }
                        ],
                    }
                ]
            }

        def describe_db_instances(self):
            return {
                "DBInstances": [
                    {
                        "DBInstanceIdentifier": "fixture",
                        "PubliclyAccessible": True,
                        "StorageEncrypted": False,
                    }
                ]
            }

    result = AWSAssessment({key: Client() for key in ("s3", "ec2", "rds")}).assess()
    assert result["partial"]
    assert len(result["findings"]) == 5
    assert result["errors"][0]["state"] == "unknown"


def test_incident_update_and_policy(client):
    login(ANALYST)
    policy = client.put("/api/v1/vader/detection-policy", headers=headers(), json={"api": 10})
    assert policy.status_code == 200, policy.text
    run = client.post("/api/v1/vader/simulator/" + identifier(), headers=headers()).json()
    incident = run[-1]["incident_id"]
    for status in ("triaged", "contained", "resolved"):
        assert (
            client.patch(
                f"/api/v1/vader/incidents/{incident}", headers=headers(), json={"status": status}
            ).status_code
            == 200
        )
    assert (
        client.patch(
            f"/api/v1/vader/incidents/{incident}", headers=headers(), json={"status": "triaged"}
        ).status_code
        == 409
    )


def test_statistical_detection_cold_start_and_tenant_baseline(client):
    from datetime import timedelta

    from app.models import now
    from conftest import DEV

    login(ANALYST)
    assert (
        client.put(
            "/api/v1/vader/detection-policy", headers=headers(), json={"api": 10000}
        ).status_code
        == 200
    )
    timestamp = now() - timedelta(minutes=2)
    for index, count in enumerate([*range(1, 21), 1000]):
        response = client.post(
            "/api/v1/vader/events",
            headers=headers(),
            json={
                "source_id": f"baseline-fixture-{index}",
                "occurred_at": (timestamp + timedelta(seconds=index)).isoformat(),
                "actor_id": DEV,
                "category": "api",
                "action": "request",
                "result": "success",
                "count": count,
            },
        )
        assert response.status_code == 201, response.text
    anomalies = client.get("/api/v1/vader/anomalies", headers=headers()).json()
    assert [anomaly["rule"] for anomaly in anomalies] == ["volume_zscore"]
    assert (
        client.get(f"/api/v1/vader/baseline/{DEV}", headers=headers()).json()["cold_start"] is False
    )
    assert (
        client.get(f"/api/v1/vader/baseline/{DEV}", headers=headers(ORG_B)).json()["cold_start"]
        is True
    )
