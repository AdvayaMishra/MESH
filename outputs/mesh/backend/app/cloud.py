"""AWS read-only posture assessment; credentials are assumed through an operator-bound role."""

import json
import time
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import HTTPException

from app.cloud_identity import AWSAccountIdentity
from app.cloud_limits import CloudInventoryLimit
from app.cloud_normalizer import CloudNormalizer
from app.core.config import settings


def pages(client, operation: str, **kwargs) -> Iterator[dict]:
    if client.can_paginate(operation):
        for number, page in enumerate(client.get_paginator(operation).paginate(**kwargs)):
            if number >= 50:
                raise CloudInventoryLimit("Cloud page inventory exceeded bound")
            yield page
    else:
        yield getattr(client, operation)(**kwargs)


class AWSAssessment:
    def __init__(
        self,
        clients: dict,
        *,
        max_assets: int = 200,
        time_budget: int = 60,
        key_age_days: int = 90,
        account_identity: AWSAccountIdentity | None = None,
        organization_id: str | None = None,
    ):
        self.clients = clients
        self.account_identity = account_identity
        self.organization_id = organization_id
        self.max_assets, self.time_budget, self.key_age_days = max_assets, time_budget, key_age_days

    def assess(self) -> dict:
        findings: list[dict] = []
        errors: list[dict] = []
        inventory = 0
        deadline = time.monotonic() + self.time_budget
        normalizer = None
        if self.account_identity is not None and self.organization_id is not None:
            regions = {
                name: region
                for name in ("ec2", "rds")
                if isinstance(
                    region := getattr(
                        getattr(self.clients[name], "meta", None), "region_name", None
                    ),
                    str,
                )
                and region
            }
            normalizer = CloudNormalizer(
                self.organization_id, self.account_identity, regions, self.max_assets
            )

        def guard():
            nonlocal inventory
            inventory += 1
            if inventory > self.max_assets or time.monotonic() > deadline:
                raise CloudInventoryLimit("Cloud inventory/time budget exceeded")

        def finding(rule, asset, severity):
            if len(findings) >= 1000:
                raise RuntimeError("Cloud finding count exceeded bound")
            findings.append(
                {
                    "rule": rule,
                    "asset": asset,
                    "severity": severity,
                    "recommendation": "Review and remediate through an independently approved change",
                }
            )

        s3 = self.clients["s3"]
        from app.cloud_resource_policies import S3PolicyInventory

        resource_policies = S3PolicyInventory(s3, normalizer, guard) if normalizer else None
        try:
            for page in pages(s3, "list_buckets"):
                for bucket in page.get("Buckets", []):
                    guard()
                    name = bucket["Name"]
                    if normalizer:
                        bucket_node = normalizer.observe("s3", "s3.bucket", native=name, name=name)
                        if resource_policies is not None:
                            resource_policies.bucket(name, bucket_node)
                    for operation, key, rule in [
                        ("get_bucket_policy_status", "PolicyStatus", "s3.public_policy"),
                        (
                            "get_bucket_encryption",
                            "ServerSideEncryptionConfiguration",
                            "s3.encryption",
                        ),
                        ("get_bucket_logging", "LoggingEnabled", "s3.logging"),
                    ]:
                        try:
                            value = getattr(s3, operation)(Bucket=name).get(key)
                            if (
                                operation == "get_bucket_policy_status"
                                and value
                                and value.get("IsPublic")
                            ):
                                finding(rule, name, "high")
                            elif operation != "get_bucket_policy_status" and not value:
                                finding(rule, name, "medium")
                        except Exception:
                            errors.append({"asset": name, "check": rule, "state": "unknown"})
        except Exception:
            errors.append({"check": "s3.inventory", "state": "unknown"})
        try:
            for page in pages(self.clients["ec2"], "describe_security_groups"):
                for group in page.get("SecurityGroups", []):
                    guard()
                    if normalizer:
                        normalizer.observe(
                            "ec2",
                            "ec2.security_group",
                            native=group.get("GroupId"),
                            name=group.get("GroupName"),
                        )
                    for rule in group.get("IpPermissions", []):
                        public = any(
                            item.get("CidrIp") == "0.0.0.0/0" for item in rule.get("IpRanges", [])
                        ) or any(
                            item.get("CidrIpv6") == "::/0" for item in rule.get("Ipv6Ranges", [])
                        )
                        if public and (
                            rule.get("IpProtocol") == "-1"
                            or any(
                                rule.get("FromPort", 0) <= port <= rule.get("ToPort", 65535)
                                for port in (22, 3389, 5432, 3306)
                            )
                        ):
                            finding("ec2.public_sensitive_port", group["GroupId"], "high")
        except Exception:
            errors.append({"check": "ec2.security_groups", "state": "unknown"})
        try:
            for page in pages(self.clients["rds"], "describe_db_instances"):
                for database in page.get("DBInstances", []):
                    guard()
                    if normalizer:
                        normalizer.observe(
                            "rds",
                            "rds.db_instance",
                            arn=database.get("DBInstanceArn"),
                            uid=database.get("DbiResourceId"),
                            native=database.get("DBInstanceIdentifier"),
                            name=database.get("DBInstanceIdentifier"),
                            facts={
                                key: database[source]
                                for key, source in (
                                    ("storage_encrypted", "StorageEncrypted"),
                                    ("reported_publicly_accessible", "PubliclyAccessible"),
                                )
                                if isinstance(database.get(source), bool)
                            },
                        )
                    if database.get("PubliclyAccessible"):
                        finding("rds.public_database", database["DBInstanceIdentifier"], "high")
                    if not database.get("StorageEncrypted"):
                        finding("rds.unencrypted", database["DBInstanceIdentifier"], "high")
        except Exception:
            errors.append({"check": "rds.inventory", "state": "unknown"})
        iam = self.clients.get("iam")
        if iam is None:
            errors.append({"check": "iam.client", "state": "unknown"})
        else:
            try:
                guard()
                summary = iam.get_account_summary()["SummaryMap"]
                if normalizer and self.account_identity is not None:
                    facts = {}
                    for field, source in (
                        ("root_console_enabled", "AccountPasswordPresent"),
                        ("root_mfa_enabled", "AccountMFAEnabled"),
                    ):
                        value = summary.get(source)
                        if type(value) is int and value in {0, 1}:
                            facts[field] = value == 1
                    keys = summary.get("AccountAccessKeysPresent")
                    if type(keys) is int and keys >= 0:
                        facts["root_access_keys_present"] = keys > 0
                    normalizer.observe(
                        "iam",
                        "iam.account_root",
                        arn=f"arn:{self.account_identity.partition}:iam::{self.account_identity.account_id}:root",
                        native=self.account_identity.account_id,
                        facts=facts,
                        operation="iam.account_summary",
                    )
                if summary.get("AccountAccessKeysPresent", 0) > 0:
                    finding("iam.root_access_key_present", "account-root", "high")
                if (
                    summary.get("AccountPasswordPresent") == 1
                    and summary.get("AccountMFAEnabled") == 0
                ):
                    finding("iam.root_console_without_mfa", "account-root", "critical")
                if any(
                    key not in summary
                    for key in (
                        "AccountMFAEnabled",
                        "AccountPasswordPresent",
                        "AccountAccessKeysPresent",
                    )
                ):
                    errors.append({"check": "iam.root_summary", "state": "unknown"})
            except Exception:
                errors.append({"check": "iam.account_summary", "state": "unknown"})
            try:
                for page in pages(iam, "list_users"):
                    for user in page.get("Users", []):
                        guard()
                        name = user["UserName"]
                        normalized_user = (
                            normalizer.observe(
                                "iam",
                                "iam.user",
                                arn=user.get("Arn"),
                                uid=user.get("UserId"),
                                name=name,
                            )
                            if normalizer
                            else None
                        )
                        try:
                            iam.get_login_profile(UserName=name)
                            if not iam.list_mfa_devices(UserName=name).get("MFADevices"):
                                finding("iam.console_user_without_mfa", name, "high")
                        except Exception as exc:
                            details = getattr(exc, "response", {})
                            code = (
                                details.get("Error", {}).get("Code")
                                if isinstance(details, dict)
                                else None
                            )
                            if code != "NoSuchEntity":
                                errors.append(
                                    {"asset": name, "check": "iam.console_mfa", "state": "unknown"}
                                )
                        try:
                            for key_page in pages(iam, "list_access_keys", UserName=name):
                                for key in key_page.get("AccessKeyMetadata", []):
                                    created = key["CreateDate"]
                                    if not isinstance(created, datetime) or created.tzinfo is None:
                                        raise ValueError("Unknown credential age")
                                    if key.get("Status") == "Active" and created < datetime.now(
                                        UTC
                                    ) - timedelta(days=self.key_age_days):
                                        finding("iam.active_key_over_age_policy", name, "medium")
                        except Exception:
                            errors.append(
                                {"asset": name, "check": "iam.key_age", "state": "unknown"}
                            )
                        try:
                            for policy_page in pages(
                                iam, "list_attached_user_policies", UserName=name
                            ):
                                for policy in policy_page.get("AttachedPolicies", []):
                                    if normalizer:
                                        normalizer.user_policy(normalized_user, policy)
                                    if str(policy.get("PolicyArn", "")).endswith(
                                        (
                                            ":aws:policy/AdministratorAccess",
                                            ":aws:policy/PowerUserAccess",
                                        )
                                    ):
                                        finding("iam.broad_managed_user_policy", name, "high")
                        except Exception:
                            errors.append(
                                {
                                    "asset": name,
                                    "check": "iam.attached_user_policies",
                                    "state": "unknown",
                                }
                            )
            except Exception:
                errors.append({"check": "iam.users", "state": "unknown"})
            try:
                for page in pages(iam, "list_roles"):
                    for role in page.get("Roles", []):
                        guard()
                        statements = role.get("AssumeRolePolicyDocument", {}).get("Statement", [])
                        if normalizer:
                            normalized_role = normalizer.observe(
                                "iam",
                                "iam.role",
                                arn=role.get("Arn"),
                                uid=role.get("RoleId"),
                                name=role.get("RoleName"),
                            )
                            normalizer.role_statements(normalized_role, statements)
                        if isinstance(statements, dict):
                            statements = [statements]
                        for statement in statements:
                            principal = statement.get("Principal", {})
                            aws = principal.get("AWS") if isinstance(principal, dict) else principal
                            actions = statement.get("Action", [])
                            actions = [actions] if isinstance(actions, str) else actions
                            wildcard = aws == "*" or isinstance(aws, list) and "*" in aws
                            if (
                                statement.get("Effect") == "Allow"
                                and wildcard
                                and any(
                                    action in {"*", "sts:*", "sts:AssumeRole"} for action in actions
                                )
                            ):
                                finding(
                                    "iam.wildcard_role_trust",
                                    role["RoleName"],
                                    "medium" if statement.get("Condition") else "critical",
                                )
            except Exception:
                errors.append({"check": "iam.role_trust", "state": "unknown"})
        if resource_policies:
            resource_policies.finish(any(error.get("check") == "s3.inventory" for error in errors))
        if normalizer and iam is not None:
            from app.cloud_iam_inventory import IAMInventory

            IAMInventory(iam, normalizer, guard).collect()
        result: dict = {
            "findings": findings,
            "errors": errors,
            "partial": bool(errors),
            "coverage": [
                "s3.policy/encryption/logging",
                "ec2.ingress",
                "rds.exposure/encryption",
                "iam.root/console_mfa/key_age/managed_user_policies/role_trust",
            ],
            "limitations": [
                "Observed read-only metadata is not a full effective-permissions analysis or a safety certification.",
                "Configured AWS region only; groups, inline policies, SCPs, boundaries and resource-policy interactions are not evaluated.",
                "Inventory/page/soft time budgets may produce partial results; SDK calls retain independent timeouts.",
            ],
        }
        if normalizer:
            result["normalized_context"] = normalizer.finish(errors, result["limitations"])
            result["partial"] = (
                result["partial"] or result["normalized_context"]["envelope"]["partial"]
            )
        return result


def configured_aws(organization_id: str) -> AWSAssessment:
    role = settings().aws_role_bindings.get(organization_id)
    if not role:
        raise HTTPException(
            503, "Read-only AWS role binding is not configured for this organization"
        )
    import boto3
    from botocore.config import Config

    config = Config(connect_timeout=5, read_timeout=10, retries={"max_attempts": 2})
    actions = [
        "s3:ListAllMyBuckets",
        "s3:GetBucketPolicyStatus",
        "s3:GetBucketPolicy",
        "s3:GetEncryptionConfiguration",
        "s3:GetBucketLogging",
        "ec2:DescribeSecurityGroups",
        "rds:DescribeDBInstances",
        "iam:GetAccountSummary",
        "iam:ListUsers",
        "iam:GetLoginProfile",
        "iam:ListMFADevices",
        "iam:ListAccessKeys",
        "iam:ListAttachedUserPolicies",
        "iam:ListRoles",
        "iam:GetAccountAuthorizationDetails",
        "iam:GetPolicy",
        "iam:GetPolicyVersion",
    ]
    try:
        identity = AWSAccountIdentity.from_role(role)
        external_id = str(UUID(organization_id))
        result = boto3.client("sts", config=config).assume_role(
            RoleArn=role,
            RoleSessionName="mesh-posture",
            DurationSeconds=900,
            ExternalId=external_id,
            Policy=json.dumps(
                {
                    "Version": "2012-10-17",
                    "Statement": [{"Effect": "Allow", "Action": actions, "Resource": "*"}],
                }
            ),
        )
        credentials = result["Credentials"]
        session = boto3.Session(
            aws_access_key_id=credentials["AccessKeyId"],
            aws_secret_access_key=credentials["SecretAccessKey"],
            aws_session_token=credentials["SessionToken"],
        )
        identity.verify_session(
            result["AssumedRoleUser"], session.client("sts", config=config).get_caller_identity()
        )
        return AWSAssessment(
            {name: session.client(name, config=config) for name in ("s3", "ec2", "rds", "iam")},
            key_age_days=settings().aws_key_max_age_days,
            account_identity=identity,
            organization_id=organization_id,
        )
    except Exception:
        raise HTTPException(503, "AWS read-only session could not be obtained") from None
