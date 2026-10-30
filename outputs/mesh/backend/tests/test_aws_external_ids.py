import boto3
import pytest
from app.aws_billing import configured_billing
from app.cloud import configured_aws
from app.core.config import settings
from conftest import ORG_A, ORG_B
from fastapi import HTTPException

ROLE = "arn:aws:iam::012345678901:role/mesh-reader"


@pytest.mark.parametrize("kind", ["posture", "billing"])
def test_each_tenant_passes_its_own_external_id_and_never_falls_back_on_denial(monkeypatch, kind):
    config = settings()
    monkeypatch.setattr(config, "aws_role_bindings", {ORG_A: ROLE, ORG_B: ROLE})
    monkeypatch.setattr(config, "aws_billing_role_bindings", {ORG_A: ROLE, ORG_B: ROLE})
    calls = []
    name = "mesh-posture" if kind == "posture" else "mesh-billing"
    assumed = {
        "Arn": f"arn:aws:sts::012345678901:assumed-role/mesh-reader/{name}",
        "AssumedRoleId": "AROAEXAMPLE123:" + name,
    }

    class STS:
        def assume_role(self, **kwargs):
            calls.append(kwargs)
            if kwargs["ExternalId"] == ORG_B:
                raise RuntimeError("PRIVATE_PROVIDER_DIAGNOSTICS")
            return {
                "Credentials": {
                    "AccessKeyId": "fixture",
                    "SecretAccessKey": "fixture",
                    "SessionToken": "fixture",
                },
                "AssumedRoleUser": assumed,
            }

        def get_caller_identity(self):
            return {
                "Account": "012345678901",
                "Arn": assumed["Arn"],
                "UserId": assumed["AssumedRoleId"],
            }

    class Session:
        def __init__(self, **kwargs):
            pass

        def client(self, name, **kwargs):
            return STS() if name == "sts" else object()

    monkeypatch.setattr(boto3, "client", lambda *a, **k: STS())
    monkeypatch.setattr(boto3, "Session", Session)
    adapter = configured_aws if kind == "posture" else configured_billing
    adapter(ORG_A)
    with pytest.raises(HTTPException) as error:
        adapter(ORG_B)
    assert error.value.status_code == 503 and "PRIVATE_PROVIDER" not in error.value.detail
    assert [call["ExternalId"] for call in calls] == [ORG_A, ORG_B]
    assert all(call["DurationSeconds"] == 900 and call["RoleSessionName"] == name for call in calls)


@pytest.mark.parametrize("kind", ["posture", "billing"])
def test_invalid_tenant_binding_fails_before_sdk_credential_or_provider_access(monkeypatch, kind):
    config = settings()
    monkeypatch.setattr(config, "aws_role_bindings", {"not-a-uuid": ROLE})
    monkeypatch.setattr(config, "aws_billing_role_bindings", {"not-a-uuid": ROLE})
    monkeypatch.setattr(boto3, "client", lambda *a, **k: pytest.fail("Invalid tenant reached SDK"))
    with pytest.raises(HTTPException) as error:
        (configured_aws if kind == "posture" else configured_billing)("not-a-uuid")
    assert error.value.status_code == 503
