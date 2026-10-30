from datetime import UTC, datetime, timedelta

from app.cloud import AWSAssessment
from app.models import CloudAssessment, identifier
from botocore.exceptions import ClientError
from conftest import ANALYST, ORG_A, ORG_B, OWNER, headers, login


class EmptyInventory:
    def can_paginate(self, operation):
        return False

    def list_buckets(self):
        return {"Buckets": []}

    def describe_security_groups(self):
        return {"SecurityGroups": []}

    def describe_db_instances(self):
        return {"DBInstances": []}


class IAM(EmptyInventory):
    def get_account_summary(self):
        return {
            "SummaryMap": {
                "AccountMFAEnabled": 0,
                "AccountPasswordPresent": 1,
                "AccountAccessKeysPresent": 1,
            }
        }

    def list_users(self):
        return {"Users": [{"UserName": "fixture-user"}]}

    def get_login_profile(self, **kwargs):
        return {"LoginProfile": {"UserName": "fixture-user"}}

    def list_mfa_devices(self, **kwargs):
        return {"MFADevices": []}

    def list_access_keys(self, **kwargs):
        return {
            "AccessKeyMetadata": [
                {
                    "Status": "Active",
                    "CreateDate": datetime.now(UTC) - timedelta(days=120),
                    "AccessKeyId": "DO_NOT_PERSIST",
                }
            ]
        }

    def list_attached_user_policies(self, **kwargs):
        return {"AttachedPolicies": [{"PolicyArn": "arn:aws:iam::aws:policy/AdministratorAccess"}]}

    def list_roles(self):
        return {
            "Roles": [
                {
                    "RoleName": "fixture-role",
                    "AssumeRolePolicyDocument": {
                        "Statement": [
                            {
                                "Effect": "Allow",
                                "Principal": {"AWS": "*"},
                                "Action": "sts:AssumeRole",
                            }
                        ],
                    },
                }
            ]
        }


def clients(iam):
    return {"s3": EmptyInventory(), "ec2": EmptyInventory(), "rds": EmptyInventory(), "iam": iam}


def test_iam_read_only_checks_explain_root_console_keys_broad_policy_and_trust():
    result = AWSAssessment(clients(IAM())).assess()
    rules = {finding["rule"] for finding in result["findings"]}
    assert rules == {
        "iam.root_access_key_present",
        "iam.root_console_without_mfa",
        "iam.console_user_without_mfa",
        "iam.active_key_over_age_policy",
        "iam.broad_managed_user_policy",
        "iam.wildcard_role_trust",
    }
    assert not result["partial"]
    assert "DO_NOT_PERSIST" not in str(result)
    assert result["limitations"]


def test_no_console_profile_is_not_mislabeled_missing_mfa_and_denials_remain_unknown():
    class NoConsole(IAM):
        def get_login_profile(self, **kwargs):
            raise ClientError({"Error": {"Code": "NoSuchEntity"}}, "GetLoginProfile")

        def list_access_keys(self, **kwargs):
            raise ClientError({"Error": {"Code": "AccessDenied"}}, "ListAccessKeys")

        def get_account_summary(self):
            return {
                "SummaryMap": {
                    "AccountMFAEnabled": 0,
                    "AccountPasswordPresent": 0,
                    "AccountAccessKeysPresent": 0,
                }
            }

    result = AWSAssessment(clients(NoConsole())).assess()
    rules = {finding["rule"] for finding in result["findings"]}
    assert "iam.root_console_without_mfa" not in rules
    assert "iam.console_user_without_mfa" not in rules
    assert result["partial"] and any(error["check"] == "iam.key_age" for error in result["errors"])


def test_cloud_inventory_bounds_return_partial_not_a_clean_assessment():
    result = AWSAssessment(clients(IAM()), max_assets=1).assess()
    assert result["partial"]
    assert any(error["check"] in {"iam.users", "iam.role_trust"} for error in result["errors"])


def test_cloud_history_retains_uncertainty_and_is_analyst_tenant_scoped(client, db):
    record = CloudAssessment(
        id=identifier(),
        organization_id=ORG_A,
        provider="aws",
        findings=[],
        partial=True,
        errors=[{"check": "iam.users", "state": "unknown"}],
        coverage=["iam.users"],
        limitations=["Access was denied; no clean assessment"],
    )
    db.add(record)
    db.commit()
    login(ANALYST)
    endpoint = "/api/v1/vader/cloud/assessments"
    assert client.get(endpoint, headers=headers()).json()[0]["errors"][0]["state"] == "unknown"
    assert client.get(endpoint + "/" + record.id, headers=headers(ORG_B)).status_code == 404
    login(OWNER)
    assert client.get(endpoint, headers=headers()).status_code == 403
