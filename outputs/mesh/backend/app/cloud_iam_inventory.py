"""Bounded IAM authorization inventory; statements are observations, never access grants."""

import hashlib
import json
import re
from typing import Literal
from urllib.parse import unquote
from uuid import uuid4

from app.cloud_context_schema import (
    Asset,
    CloudPrincipal,
    Coverage,
    NodeRef,
    PermissionObservation,
    Relationship,
    Scope,
)
from app.cloud_limits import CloudInventoryLimit

LAYERS = (
    "users",
    "roles",
    "groups_membership",
    "managed_policy_documents",
    "inline_policies",
    "boundaries",
    "trust_policies",
)


def policy_document(value) -> dict:
    if isinstance(value, str):
        if len(value) > 512 * 1024:
            raise ValueError("Policy exceeds byte bound")
        text = (
            value
            if value.lstrip().startswith("{")
            else unquote(value, encoding="utf-8", errors="strict")
        )
        value = json.loads(text)
    if not isinstance(value, dict):
        raise ValueError("Policy must be an object")
    queue = [(value, 0)]
    visited = 0
    while queue:
        item, depth = queue.pop()
        visited += 1
        if visited > 10000 or depth > 32:
            raise ValueError("Policy structure exceeds bound")
        if isinstance(item, dict):
            queue.extend((child, depth + 1) for child in item.values())
        elif isinstance(item, list):
            queue.extend((child, depth + 1) for child in item)
    if len(json.dumps(value, allow_nan=False).encode()) > 512 * 1024:
        raise ValueError("Policy exceeds byte bound")
    return value


def node_ref(node):
    return (
        NodeRef(kind="asset", key=node.asset_key)
        if isinstance(node, Asset)
        else NodeRef(kind="principal", key=node.principal_key)
    )


class IAMInventory:
    def __init__(self, client, normalizer, guard):
        self.client, self.graph, self.guard = client, normalizer, guard
        self.groups = {}
        self.users = []
        self.subjects = []
        self.documents = {}
        self.policy_nodes = {}
        self.layers: dict[str, Literal["complete", "partial", "denied"]] = {
            layer: "complete" for layer in LAYERS
        }
        self.counts = {layer: 0 for layer in LAYERS}
        self.reasons = {}
        self.truncated = set()

    def failed(self, layer, error):
        response = getattr(error, "response", {})
        code = response.get("Error", {}).get("Code") if isinstance(response, dict) else None
        denied = code in {"AccessDenied", "AccessDeniedException", "UnauthorizedOperation"}
        self.layers[layer] = "denied" if denied else "partial"
        reason = (
            "budget_exceeded"
            if isinstance(error, CloudInventoryLimit)
            else "access_denied"
            if denied
            else "provider_unavailable"
        )
        self.reasons[layer] = reason
        if isinstance(error, CloudInventoryLimit):
            self.truncated.add(layer)
        if len(self.graph.errors) < 1000:
            self.graph.errors.append(reason)

    def link(self, source, target, kind, reference=None, condition_state="unknown"):
        self.guard()
        if len(self.graph.relationships) >= 1000:
            raise CloudInventoryLimit("Relationship bound exceeded")
        left, right = node_ref(source), node_ref(target)
        if kind not in {"trusts_principal", "resource_policy_references"} and any(
            edge.from_ == left and edge.to == right and edge.relationship_type == kind
            for edge in self.graph.relationships
        ):
            return
        times = self.graph.times()
        reference = reference or self.graph.retain(
            "iam.authorization_relationship", {"node_type": source.node_type}, times
        )
        self.graph.relationships.append(
            Relationship.model_validate(
                {
                    "organization_id": self.graph.organization_id,
                    "assessment_id": self.graph.assessment_id,
                    "relationship_id": uuid4(),
                    "from": left,
                    "to": right,
                    "relationship_type": kind,
                    "basis": "policy_derived"
                    if kind in {"trusts_principal", "resource_policy_references"}
                    else "provider_observed",
                    "resolution": "external_reference"
                    if target.lifecycle_state == "unknown"
                    else "resolved",
                    "condition_state": condition_state,
                    "timestamps": times,
                    "evidence_refs": [reference],
                }
            )
        )

    def principal_reference(self, value, principal_kind, reference, times):
        if not isinstance(value, str) or value == "*":
            return None
        if principal_kind == "AWS" and re.fullmatch(r"[0-9]{12}", value):
            value = f"arn:{self.graph.identity.partition}:iam::{value}:root"
        existing = [
            node
            for node in self.graph.nodes.values()
            if isinstance(node, CloudPrincipal) and node.arn == value
        ]
        if len(existing) == 1:
            return existing[0]
        if existing:
            raise ValueError("Ambiguous principal reference")
        account = None
        native = None
        service = "iam"
        if principal_kind == "Service":
            if not re.fullmatch(r"[a-z0-9.-]{1,240}\.amazonaws\.com(?:\.cn)?", value):
                raise ValueError("Unsupported service reference")
            node_type, ownership, namespace, native = (
                "aws.service_principal",
                "aws_service",
                "aws-service",
                value,
            )
            arn = None
        else:
            match = re.fullmatch(r"arn:(aws|aws-us-gov|aws-cn):(iam|sts)::([0-9]{12}):(.+)", value)
            if not match or match[1] != self.graph.identity.partition:
                raise ValueError("Unsupported principal reference")
            service, account, arn, resource = match[2], match[3], value, match[4]
            if service == "iam" and re.fullmatch(r"root|(?:user|role)/[^*?]+", resource):
                node_type = (
                    "iam.account_root" if resource == "root" else "iam." + resource.split("/", 1)[0]
                )
                if resource == "root":
                    native = account
            elif service == "sts" and re.fullmatch(
                r"assumed-role/[A-Za-z0-9_+=,.@-]{1,64}/[A-Za-z0-9_+=,.@-]{1,64}", resource
            ):
                node_type = "sts.assumed_role_session"
                if "sts" not in self.graph.scopes:
                    self.graph.scopes["sts"] = Scope.model_validate(
                        {**self.graph.scopes["iam"].model_dump(), "service": "sts"}
                    )
            else:
                raise ValueError("Unsupported principal reference")
            ownership = (
                "bound_account" if account == self.graph.identity.account_id else "external_account"
            )
            namespace = account
        from app.cloud_keys import cloud_node_key

        provider_identity = arn or native
        if not isinstance(provider_identity, str):
            raise ValueError("Missing principal reference")
        key = cloud_node_key(
            organization_id=self.graph.organization_id,
            partition=self.graph.identity.partition,
            owner_namespace=namespace,
            service=service,
            region=None,
            node_type=node_type,
            identity_kind="arn" if arn else "scoped_native_id",
            provider_identity=provider_identity,
        )
        if key in self.graph.nodes:
            return self.graph.nodes[key]
        if len(self.graph.nodes) >= self.graph.max_nodes:
            raise CloudInventoryLimit("Reference node budget exceeded")
        node = CloudPrincipal.model_validate(
            {
                "organization_id": self.graph.organization_id,
                "assessment_id": self.graph.assessment_id,
                "node_type": node_type,
                "scope": self.graph.scopes[service],
                "ownership": ownership,
                "owner_account_id": account,
                "identity_kind": "arn" if arn else "scoped_native_id",
                "identity_strength": "scoped_reference",
                "provider_uid": None,
                "arn": arn,
                "native_id": native,
                "incarnation_ref": None,
                "display_name": None,
                "lifecycle_state": "unknown",
                "timestamps": times,
                "facts": {},
                "evidence_refs": [reference],
                "principal_key": key,
                "principal_type": "service_principal"
                if principal_kind == "Service"
                else "external_reference",
            }
        )
        self.graph.nodes[key] = node
        return node

    def trust_targets(
        self,
        subject,
        statement,
        reference,
        times,
        condition_state,
        relationship_type="trusts_principal",
    ):
        if relationship_type == "trusts_principal" and statement["Effect"] != "Allow":
            return
        principal = statement.get("Principal", {})
        if principal == "*" or "NotPrincipal" in statement:
            return
        if not isinstance(principal, dict) or set(principal) - {"AWS", "Service"}:
            raise ValueError("Unsupported trust principal kind")
        for kind, values in principal.items():
            values = [values] if isinstance(values, str) else values
            if not isinstance(values, list) or len(values) > 100:
                raise ValueError("Trust target count exceeded")
            for value in values:
                self.guard()
                target = self.principal_reference(value, kind, reference, times)
                if target is not None:
                    self.link(subject, target, relationship_type, reference, condition_state)

    def statements(self, subject, document, kind, *, policy_arn=None, version=None):
        document = policy_document(document)
        statements = document.get("Statement")
        statements = [statements] if isinstance(statements, dict) else statements
        if not isinstance(statements, list) or not 1 <= len(statements) <= 100:
            raise ValueError("Invalid or oversized statement list")
        for index, statement in enumerate(statements):
            self.guard()
            if len(self.graph.permissions) >= 1000 or not isinstance(statement, dict):
                raise ValueError("Statement bound exceeded")
            times = self.graph.times()
            condition = statement.get("Condition")
            if "Condition" in statement and not isinstance(condition, dict):
                raise ValueError("Unknown condition structure")

            def selector(field, statement=statement):
                value = statement.get(field, [])
                return [value] if isinstance(value, str) else value

            subject_ref = node_ref(subject)
            data = {
                "organization_id": self.graph.organization_id,
                "assessment_id": self.graph.assessment_id,
                "permission_id": uuid4(),
                "subject_ref": subject_ref,
                "principal_key": subject.principal_key
                if isinstance(subject, CloudPrincipal)
                else None,
                "policy_arn": policy_arn,
                "policy_version_ref": version,
                "statement_index": index,
                "policy_kind": kind,
                "observed_effect": statement["Effect"],
                "actions": selector("Action"),
                "not_actions": selector("NotAction"),
                "resources": selector("Resource"),
                "not_resources": selector("NotResource"),
                "condition_state": "present" if "Condition" in statement else "absent",
                "condition_digest": hashlib.sha256(
                    json.dumps(condition, sort_keys=True, separators=(",", ":")).encode()
                ).hexdigest()
                if "Condition" in statement
                else None,
                "unknown_dependencies": [
                    "session",
                    "scp",
                    "rcp",
                    "resource_policies",
                    "request_context",
                ],
                "timestamps": times,
                "evidence_refs": subject.evidence_refs,
            }
            permission = PermissionObservation.model_validate(data)
            reference = self.graph.retain(
                "iam.policy_statement",
                {
                    "node_type": subject.node_type,
                    "statement_index": index,
                    "effect": statement["Effect"],
                    "condition_state": permission.condition_state,
                    **({"policy_arn": policy_arn} if policy_arn else {}),
                },
                times,
            )
            self.graph.permissions.append(
                permission.model_copy(update={"evidence_refs": [reference]})
            )
            if kind in {"trust", "resource"}:
                self.trust_targets(
                    subject,
                    statement,
                    reference,
                    times,
                    permission.condition_state,
                    "trusts_principal" if kind == "trust" else "resource_policy_references",
                )

    def managed(self, arn):
        if arn in self.documents:
            return self.policy_nodes[arn], self.documents[arn]
        self.guard()
        profile = self.client.get_policy(PolicyArn=arn)["Policy"]
        if profile.get("Arn") != arn:
            raise ValueError("Policy identity changed")
        node = self.graph.observe(
            "iam",
            "iam.policy",
            arn=arn,
            uid=profile.get("PolicyId"),
            name=profile.get("PolicyName"),
        )
        if node is None:
            raise ValueError("Policy identity unresolved")
        version = profile["DefaultVersionId"]
        self.guard()
        response = self.client.get_policy_version(PolicyArn=arn, VersionId=version)["PolicyVersion"]
        if response.get("VersionId") != version or response.get("IsDefaultVersion") is not True:
            raise ValueError("Policy version changed during observation")
        document = policy_document(response["Document"])
        self.policy_nodes[arn], self.documents[arn] = node, (document, version)
        self.counts["managed_policy_documents"] += 1
        return node, (document, version)

    def details(self, node, row, prefix):
        for inline in row.get(prefix + "PolicyList", []):
            try:
                self.statements(
                    node, inline["PolicyDocument"], "identity_inline", version=inline["PolicyName"]
                )
                self.counts["inline_policies"] += 1
            except Exception as error:
                self.failed("inline_policies", error)
        for attached in row.get("AttachedManagedPolicies", []):
            try:
                self.guard()
                policy, (document, version) = self.managed(attached["PolicyArn"])
                self.link(node, policy, "policy_attached")
                self.statements(
                    node,
                    document,
                    "identity_managed",
                    policy_arn=attached["PolicyArn"],
                    version=version,
                )
            except Exception as error:
                self.failed("managed_policy_documents", error)
        boundary = row.get("PermissionsBoundary")
        if boundary:
            try:
                self.guard()
                arn = boundary["PermissionsBoundaryArn"]
                policy, (document, version) = self.managed(arn)
                self.link(node, policy, "boundary_attached")
                self.statements(
                    node, document, "permissions_boundary", policy_arn=arn, version=version
                )
                self.counts["boundaries"] += 1
            except Exception as error:
                self.failed("boundaries", error)

    def collect(self):
        try:
            marker = None
            seen = set()
            for _ in range(50):
                self.guard()
                page = self.client.get_account_authorization_details(
                    Filter=["User", "Role", "Group"],
                    MaxItems=50,
                    **({"Marker": marker} if marker else {}),
                )
                if len(json.dumps(page, default=str).encode()) > 2 * 1024 * 1024:
                    raise ValueError("IAM response exceeds byte bound")
                for collection, prefix, uid_field in (
                    ("GroupDetailList", "Group", "GroupId"),
                    ("UserDetailList", "User", "UserId"),
                    ("RoleDetailList", "Role", "RoleId"),
                ):
                    rows = page.get(collection, [])
                    if not isinstance(rows, list) or len(rows) > 50:
                        raise ValueError("Invalid IAM page shape")
                    for row in rows:
                        self.guard()
                        node = self.graph.observe(
                            "iam",
                            "iam." + prefix.lower(),
                            arn=row.get("Arn"),
                            uid=row.get(uid_field),
                            name=row.get(prefix + "Name"),
                        )
                        if node is None:
                            raise ValueError("IAM subject identity unresolved")
                        self.subjects.append((node, row, prefix))
                        if prefix == "Group":
                            name = row["GroupName"]
                            if name in self.groups and self.groups[name] != node:
                                raise ValueError("Ambiguous group identity")
                            self.groups[name] = node
                        elif prefix == "User":
                            self.users.append((node, row))
                            self.counts["users"] += 1
                        else:
                            self.counts["roles"] += 1
                if page.get("IsTruncated") is False:
                    break
                marker = page.get("Marker")
                if (
                    not isinstance(marker, str)
                    or not marker
                    or len(marker) > 2048
                    or marker in seen
                ):
                    raise ValueError("Invalid IAM continuation")
                seen.add(marker)
            else:
                raise CloudInventoryLimit("IAM page bound exceeded")
            for node, row, prefix in self.subjects:
                self.details(node, row, prefix)
                if prefix == "Role":
                    try:
                        self.statements(node, row["AssumeRolePolicyDocument"], "trust")
                        self.counts["trust_policies"] += 1
                    except Exception as error:
                        self.failed("trust_policies", error)
            for user, row in self.users:
                try:
                    groups = row.get("GroupList", [])
                    if not isinstance(groups, list) or len(groups) > 1000:
                        raise ValueError("Invalid group membership list")
                    for name in groups:
                        if name not in self.groups:
                            raise ValueError("Membership target not collected")
                        self.link(user, self.groups[name], "member_of")
                        self.counts["groups_membership"] += 1
                except Exception as error:
                    self.failed("groups_membership", error)
        except Exception as error:
            for layer in LAYERS:
                self.failed(layer, error)
        for layer in LAYERS:
            self.graph.layer_coverage[layer] = Coverage(
                scope=self.graph.scopes["iam"],
                check="iam." + layer,
                state=self.layers[layer],
                timestamps=self.graph.times(),
                observed_count=self.counts[layer],
                expected_total=None,
                configured_limit=self.graph.max_nodes,
                truncated=layer in self.truncated,
                reason_code=None
                if self.layers[layer] == "complete"
                else self.reasons.get(layer, "not_collected"),
            )
