from copy import deepcopy
from types import SimpleNamespace

import boto3
import pytest
from app import cloud
from app.cloud_identity import AWSAccountIdentity
from conftest import ORG_A
from fastapi import HTTPException

ROLE = "arn:aws:iam::012345678901:role/security/mesh-reader"
ASSUMED = {
    "Arn": "arn:aws:sts::012345678901:assumed-role/mesh-reader/mesh-posture",
    "AssumedRoleId": "AROAEXAMPLE123:mesh-posture",
}
CALLER = {"Account": "012345678901", "Arn": ASSUMED["Arn"], "UserId": ASSUMED["AssumedRoleId"]}


@pytest.mark.parametrize("partition", ["aws", "aws-us-gov", "aws-cn"])
def test_bound_account_verifies_paths_and_leading_zero_account(partition):
    identity = AWSAccountIdentity.from_role(ROLE.replace("arn:aws:", f"arn:{partition}:"))
    assumed = {
        key: value.replace("arn:aws:", f"arn:{partition}:") for key, value in ASSUMED.items()
    }
    caller = {key: value.replace("arn:aws:", f"arn:{partition}:") for key, value in CALLER.items()}
    identity.verify_session(assumed, caller)
    assert identity.account_id == "012345678901"


@pytest.mark.parametrize(
    "role",
    [
        "",
        ROLE + "/",
        ROLE.replace("role/", "user/"),
        ROLE.replace("012345678901", "123"),
        ROLE.replace("security/", "security//"),
        ROLE.replace("aws:", "other:"),
    ],
)
def test_rejects_invalid_role_binding(role):
    with pytest.raises(ValueError):
        AWSAccountIdentity.from_role(role)


@pytest.mark.parametrize(
    "field,value",
    [
        ("Account", "999999999999"),
        ("Account", 12345678901),
        ("Arn", ASSUMED["Arn"] + "other"),
        ("UserId", "AROAOTHER:mesh-posture"),
    ],
)
def test_rejects_mismatched_target_credentials(field, value):
    caller = {**CALLER, field: value}
    with pytest.raises(ValueError):
        AWSAccountIdentity.from_role(ROLE).verify_session(ASSUMED, caller)


def test_configured_collection_verifies_before_inventory(monkeypatch):
    calls = []
    caller = deepcopy(CALLER)

    class STS:
        def assume_role(self, **kwargs):
            assert kwargs["RoleArn"] == ROLE
            assert kwargs["ExternalId"] == ORG_A
            return {
                "Credentials": {
                    "AccessKeyId": "fixture",
                    "SecretAccessKey": "fixture",
                    "SessionToken": "fixture",
                },
                "AssumedRoleUser": ASSUMED,
            }

        def get_caller_identity(self):
            calls.append("verify")
            return caller

    class Session:
        def __init__(self, **kwargs):
            pass

        def client(self, name, **kwargs):
            calls.append(name)
            return STS() if name == "sts" else object()

    monkeypatch.setattr(
        cloud,
        "settings",
        lambda: SimpleNamespace(aws_role_bindings={ORG_A: ROLE}, aws_key_max_age_days=90),
    )
    monkeypatch.setattr(boto3, "client", lambda *args, **kwargs: STS())
    monkeypatch.setattr(boto3, "Session", Session)
    assert cloud.configured_aws(ORG_A).account_identity.account_id == "012345678901"
    assert calls == ["sts", "verify", "s3", "ec2", "rds", "iam"]
    calls.clear()
    caller["Account"] = "999999999999"
    with pytest.raises(HTTPException) as error:
        cloud.configured_aws(ORG_A)
    assert error.value.status_code == 503
    assert calls == ["sts", "verify"]
    assert "999999999999" not in error.value.detail


@pytest.mark.parametrize(
    "assumed",
    [
        {},
        {"Arn": None, "AssumedRoleId": None},
        {**ASSUMED, "Arn": ASSUMED["Arn"].replace("mesh-reader/", "other-role/")},
        {**ASSUMED, "AssumedRoleId": "AROAEXAMPLE123:other-session"},
        {**ASSUMED, "Arn": ASSUMED["Arn"].replace("arn:aws:", "arn:aws-cn:")},
    ],
)
def test_malformed_or_wrong_assumed_identity_cannot_self_attest(assumed):
    caller = {
        "Account": "012345678901",
        "Arn": assumed.get("Arn"),
        "UserId": assumed.get("AssumedRoleId"),
    }
    with pytest.raises(ValueError):
        AWSAccountIdentity.from_role(ROLE).verify_session(assumed, caller)


def test_unbound_tenant_never_contacts_aws(monkeypatch):
    monkeypatch.setattr(cloud, "settings", lambda: SimpleNamespace(aws_role_bindings={}))

    def unexpected(*args, **kwargs):
        pytest.fail("Unbound tenant contacted AWS")

    monkeypatch.setattr(boto3, "client", unexpected)
    with pytest.raises(HTTPException) as error:
        cloud.configured_aws("unbound")
    assert error.value.status_code == 503
