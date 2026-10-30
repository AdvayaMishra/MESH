"""Stable, tenant-scoped node keys for mesh.cloud-context 1.x producers.

This module assigns identifiers only; it does not verify provider observations or
claim that an asset exists, permissions are effective, or inventory is complete.
"""

import hashlib
import json
import re
from typing import Literal
from uuid import UUID

_SCOPES = {
    "s3.bucket": ("s3", "global", "asset"),
    "ec2.security_group": ("ec2", "regional", "asset"),
    "rds.db_instance": ("rds", "regional", "asset"),
    "iam.group": ("iam", "global", "asset"),
    "aws.service_principal": ("iam", "global", "principal"),
    "iam.policy": ("iam", "global", "asset"),
    "iam.user": ("iam", "global", "principal"),
    "iam.role": ("iam", "global", "principal"),
    "iam.account_root": ("iam", "global", "principal"),
    "sts.assumed_role_session": ("sts", "global", "principal"),
}


def cloud_node_key(
    *,
    organization_id: str,
    partition: Literal["aws", "aws-us-gov", "aws-cn"],
    owner_namespace: str,
    service: str,
    region: str | None,
    node_type: str,
    identity_kind: Literal["provider_uid", "arn", "scoped_native_id"],
    provider_identity: str,
) -> str:
    """Encode a supported type's canonical tuple; callers must establish ownership.

    With only string array elements, compact UTF-8 JSON has the RFC 8785 JCS
    representation. Reject surrogate code points rather than replacing bytes.
    Unknown node types require an explicit scope rule before this helper supports them.
    """
    tenant = str(UUID(organization_id))
    if partition not in {"aws", "aws-us-gov", "aws-cn"}:
        raise ValueError("Unsupported cloud partition")
    if not re.fullmatch(r"[0-9]{12}|aws-managed|aws-service|unknown:[0-9]{12}", owner_namespace):
        raise ValueError("Invalid cloud owner namespace")
    scope = _SCOPES.get(node_type)
    if scope is None or service != scope[0]:
        raise ValueError("Unsupported cloud node scope")
    if scope[1] == "global" and region is not None:
        raise ValueError("Global cloud nodes must not have a region")
    if scope[1] == "regional" and (
        not isinstance(region, str)
        or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)+", region)
        or len(region) > 64
    ):
        raise ValueError("Regional cloud nodes require an explicit region")
    if identity_kind not in {"provider_uid", "arn", "scoped_native_id"}:
        raise ValueError("Unsupported cloud identity kind")
    bound = 2048 if identity_kind == "arn" else 256
    if (
        not isinstance(provider_identity, str)
        or not provider_identity
        or len(provider_identity) > bound
    ):
        raise ValueError("Invalid provider identity length")
    if any(
        ord(character) < 32 or 0xD800 <= ord(character) <= 0xDFFF for character in provider_identity
    ):
        raise ValueError("Invalid provider identity text")
    if node_type == "aws.service_principal" and (
        owner_namespace != "aws-service"
        or identity_kind != "scoped_native_id"
        or not re.fullmatch(r"[a-z0-9.-]{1,240}\.amazonaws\.com(?:\.cn)?", provider_identity)
    ):
        raise ValueError("Invalid AWS service principal identity")
    if identity_kind == "arn":
        parts = provider_identity.split(":", 5)
        expected_owner = "aws" if owner_namespace == "aws-managed" else owner_namespace
        resource_prefix = {
            "iam.user": "user/",
            "iam.role": "role/",
            "iam.group": "group/",
            "iam.policy": "policy/",
            "iam.account_root": "root",
            "sts.assumed_role_session": "assumed-role/",
            "ec2.security_group": "security-group/",
            "rds.db_instance": "db:",
            "s3.bucket": "",
        }[node_type]
        if (
            len(parts) != 6
            or parts[:3] != ["arn", partition, service]
            or parts[3] != (region or "")
            or not parts[5]
            or parts[4] != ("" if service == "s3" else expected_owner)
            or not parts[5].startswith(resource_prefix)
            or (resource_prefix and parts[5] == resource_prefix and node_type != "iam.account_root")
            or (node_type == "iam.account_root" and parts[5] != "root")
            or (node_type == "s3.bucket" and "/" in parts[5])
        ):
            raise ValueError("Provider ARN does not match declared scope")
    values = [
        "mesh-cloud-identity-v1",
        tenant,
        "aws",
        partition,
        owner_namespace,
        service,
        region or "",
        node_type,
        identity_kind,
        provider_identity,
    ]
    digest = hashlib.sha256(
        json.dumps(values, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return ("ca1_" if scope[2] == "asset" else "cp1_") + digest
