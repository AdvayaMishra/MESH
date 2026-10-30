"""Normalize bounded, actually observed AWS inventory; never infer effective access."""

import hashlib
import json
from datetime import timedelta
from typing import Literal
from uuid import UUID, uuid4

from app.cloud_context_schema import (
    Asset,
    CloudPrincipal,
    Coverage,
    Envelope,
    EvidenceObservation,
    EvidenceRef,
    Fact,
    NodeRef,
    PermissionObservation,
    Relationship,
    Scope,
    Snapshot,
    Times,
)
from app.cloud_identity import AWSAccountIdentity
from app.cloud_keys import cloud_node_key
from app.models import now


class CloudNormalizer:
    def __init__(
        self,
        organization_id: str,
        identity: AWSAccountIdentity,
        regions: dict[str, str],
        max_assets: int,
    ):
        self.organization_id, self.identity = organization_id, identity
        self.assessment_id = uuid4()
        self.started = now()
        self.scopes = {
            service: Scope(
                organization_id=UUID(organization_id),
                partition=identity.partition,
                provider_account_id=identity.account_id,
                service=service,
                scope_kind="global" if service in {"s3", "iam"} else "regional",
                region=None if service in {"s3", "iam"} else regions[service],
            )
            for service in ("s3", "iam", *regions)
        }
        self.nodes: dict[str, Asset | CloudPrincipal] = {}
        self.evidence: list[EvidenceObservation] = []
        self.permissions: list[PermissionObservation] = []
        self.relationships: list[Relationship] = []
        self.errors: list[str] = []
        self.layer_coverage: dict[str, Coverage] = {}
        self.max_nodes = min(max_assets * 3, 10000)

    def times(self):
        observed = now()
        return Times(
            observed_at=observed, collected_at=observed, fresh_until=observed + timedelta(hours=1)
        )

    def retain(self, operation, summary, times):
        reference = EvidenceRef(
            organization_id=UUID(self.organization_id),
            assessment_id=self.assessment_id,
            evidence_id=uuid4(),
            source_kind="policy_statement"
            if operation in {"iam.role_trust_statement", "iam.policy_statement"}
            else "provider_response",
            operation=operation,
            observed_at=times.observed_at,
            content_digest=hashlib.sha256(
                json.dumps(summary, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest(),
            verification="provider_observed",
        )
        self.evidence.append(
            EvidenceObservation(reference=reference, availability="available", summary=summary)
        )
        return reference

    def observe(
        self,
        service: str,
        node_type: str,
        *,
        arn=None,
        uid=None,
        native=None,
        name=None,
        facts=None,
        operation=None,
    ):
        """Only called with allowlisted fields from an inventory response."""
        try:
            scope = self.scopes[service]
            owner = (
                "aws-managed"
                if arn and arn.startswith(f"arn:{self.identity.partition}:iam::aws:policy/")
                else self.identity.account_id
            )
            kind: Literal["provider_uid", "arn", "scoped_native_id"] = (
                "provider_uid" if uid else "arn" if arn else "scoped_native_id"
            )
            if arn:
                cloud_node_key(
                    organization_id=self.organization_id,
                    partition=scope.partition,
                    owner_namespace=owner,
                    service=service,
                    region=scope.region,
                    node_type=node_type,
                    identity_kind="arn",
                    provider_identity=arn,
                )
            key = cloud_node_key(
                organization_id=self.organization_id,
                partition=scope.partition,
                owner_namespace=owner,
                service=service,
                region=scope.region,
                node_type=node_type,
                identity_kind=kind,
                provider_identity=uid or arn or native,
            )
            if key in self.nodes:
                return self.nodes[key]
            if len(self.nodes) >= self.max_nodes:
                raise ValueError("Node budget exceeded")
            times = self.times()
            summary = {
                "node_type": node_type,
                **({"arn": arn} if arn else {}),
                **({"provider_uid": uid} if uid else {}),
                **({"native_id": native} if native else {}),
                **(facts or {}),
            }
            ref = self.retain(operation or service + ".inventory", summary, times)
            data = dict(
                organization_id=UUID(self.organization_id),
                assessment_id=self.assessment_id,
                node_type=node_type,
                scope=scope,
                ownership="aws_managed" if owner == "aws-managed" else "bound_account",
                owner_account_id=None if owner == "aws-managed" else owner,
                identity_kind=kind,
                identity_strength="provider_uid" if uid else "scoped_reference",
                provider_uid=uid,
                arn=arn,
                native_id=native,
                incarnation_ref=uid,
                display_name=name,
                lifecycle_state="observed_present",
                timestamps=times,
                facts={
                    field: Fact(value=value, state="known", evidence_refs=[ref])
                    for field, value in (facts or {}).items()
                    if value is not None
                },
                evidence_refs=[ref],
            )
            if key.startswith("cp1_"):
                principal_type = {
                    "iam.user": "iam_user",
                    "iam.role": "iam_role",
                    "iam.account_root": "account_root",
                }[node_type]
                node: Asset | CloudPrincipal = CloudPrincipal.model_validate(
                    {**data, "principal_key": key, "principal_type": principal_type}
                )
            else:
                node = Asset(asset_key=key, **data)
            self.nodes[key] = node
            return node
        except (ValueError, KeyError, TypeError):
            if len(self.errors) < 1000:
                self.errors.append("identity_unresolved")
            return None

    def user_policy(self, user, policy):
        if len(self.relationships) >= 1000:
            if len(self.errors) < 1000:
                self.errors.append("budget_exceeded")
            return
        if user is None:
            return
        node = self.observe(
            "iam", "iam.policy", arn=policy.get("PolicyArn"), name=policy.get("PolicyName")
        )
        if node is not None:
            self.relationships.append(
                Relationship.model_validate(
                    {
                        "organization_id": self.organization_id,
                        "assessment_id": self.assessment_id,
                        "relationship_id": uuid4(),
                        "from": {"kind": "principal", "key": user.principal_key},
                        "to": {"kind": "asset", "key": node.asset_key},
                        "relationship_type": "policy_attached",
                        "basis": "provider_observed",
                        "resolution": "resolved",
                        "condition_state": "unknown",
                        "timestamps": node.timestamps,
                        "evidence_refs": node.evidence_refs,
                    }
                )
            )

    def role_statements(self, role, statements):
        if role is None:
            return
        if isinstance(statements, dict):
            statements = [statements]
        if not isinstance(statements, list) or len(statements) > 1000:
            self.errors.append("budget_exceeded")
            return
        for index, statement in enumerate(statements):
            try:
                if len(self.permissions) >= 1000:
                    raise ValueError("Statement bound exceeded")
                times = self.times()
                condition = statement.get("Condition")
                condition_state: Literal["present", "absent"] = "present" if condition else "absent"
                digest = (
                    hashlib.sha256(
                        json.dumps(condition, sort_keys=True, separators=(",", ":")).encode()
                    ).hexdigest()
                    if condition
                    else None
                )
                summary = {
                    "node_type": "iam.role",
                    "statement_index": index,
                    "effect": statement["Effect"],
                    "condition_state": condition_state,
                }

                # Validate before retaining evidence; never retain the raw principal/condition document.
                def selectors(field, statement=statement):
                    value = statement.get(field, [])
                    return [value] if isinstance(value, str) else value

                permission = PermissionObservation(
                    organization_id=UUID(self.organization_id),
                    assessment_id=self.assessment_id,
                    permission_id=uuid4(),
                    subject_ref=NodeRef(kind="principal", key=role.principal_key),
                    principal_key=role.principal_key,
                    policy_arn=role.arn,
                    policy_version_ref=None,
                    statement_index=index,
                    policy_kind="trust",
                    observed_effect=statement["Effect"],
                    actions=selectors("Action"),
                    not_actions=selectors("NotAction"),
                    resources=selectors("Resource"),
                    not_resources=selectors("NotResource"),
                    condition_state=condition_state,
                    condition_digest=digest,
                    unknown_dependencies=[
                        "identity_policies",
                        "session",
                        "boundaries",
                        "scp",
                        "rcp",
                        "resource_policies",
                        "request_context",
                        "trust_principal_selector",
                    ],
                    timestamps=times,
                    evidence_refs=role.evidence_refs,
                )
                ref = self.retain("iam.role_trust_statement", summary, times)
                self.permissions.append(permission.model_copy(update={"evidence_refs": [ref]}))
            except (ValueError, KeyError, TypeError):
                if len(self.errors) < 1000:
                    self.errors.append("conditions_unresolved")

    def finish(self, errors, limitations):
        coverage = []
        for service, scope in self.scopes.items():
            failed = any(error.get("check", "").startswith(service + ".") for error in errors)
            nodes = [node for node in self.nodes.values() if node.scope.service == service]
            coverage.append(
                Coverage(
                    scope=scope,
                    check=service + ".inventory",
                    state="partial"
                    if service in {"iam", "sts"} or failed or self.errors
                    else "complete",
                    timestamps=self.times(),
                    observed_count=len(nodes),
                    expected_total=None,
                    configured_limit=self.max_nodes,
                    truncated=False,
                    reason_code="provider_unavailable"
                    if failed
                    else "identity_unresolved"
                    if self.errors
                    else None,
                )
            )
        for layer in (
            "groups_membership",
            "managed_policy_documents",
            "inline_policies",
            "resource_policies",
            "boundaries",
            "session_policies",
            "scp",
            "rcp",
            "acl",
        ):
            coverage.append(
                Coverage(
                    scope=self.scopes["iam"],
                    check="iam." + layer,
                    state="unsupported",
                    timestamps=self.times(),
                    observed_count=0,
                    expected_total=None,
                    configured_limit=self.max_nodes,
                    truncated=False,
                    reason_code="unsupported_policy_layer",
                )
            )
        coverage = [
            entry
            for entry in coverage
            if entry.check.removeprefix("iam.") not in self.layer_coverage
        ]
        coverage.extend(self.layer_coverage.values())
        collected = now()
        envelope = Envelope(
            organization_id=UUID(self.organization_id),
            assessment_id=self.assessment_id,
            source_job_id=None,
            scope=Scope(
                organization_id=UUID(self.organization_id),
                partition=self.identity.partition,
                provider_account_id=self.identity.account_id,
                service="account",
                scope_kind="account",
                region=None,
            ),
            requested_scopes=list(self.scopes.values()),
            binding_ref="aws-role-binding",
            binding_revision=hashlib.sha256(self.identity.role_arn.encode()).hexdigest(),
            normalizer_version="mesh-aws-normalizer-3",
            collector_version="mesh-aws-posture-2",
            synthetic=False,
            provenance="provider_observed",
            collection_started_at=self.started,
            collection_finished_at=collected,
            collected_at=collected,
            coverage=coverage,
            partial=True,
            limits={
                "nodes": self.max_nodes,
                "permissions": 1000,
                "inventory_entries": self.max_nodes // 3,
                "pages_per_operation": 50,
            },
            errors=sorted(
                set(
                    self.errors
                    + (["provider_unavailable"] if errors else [])
                    + (
                        ["identity_unresolved"]
                        if not {"s3", "iam", "ec2", "rds"}.issubset(self.scopes)
                        else []
                    )
                )
            ),
            limitations=[
                *limitations,
                "IAM effective permissions are not evaluated; unsupported policy layers remain explicit.",
                "Evidence digests cover retained allowlisted summaries, not full provider responses.",
            ],
        )
        return Snapshot(
            envelope=envelope,
            assets=[node for node in self.nodes.values() if isinstance(node, Asset)],
            principals=[node for node in self.nodes.values() if isinstance(node, CloudPrincipal)],
            permissions=self.permissions,
            relationships=self.relationships,
            evidence=self.evidence,
        ).model_dump(mode="json", by_alias=True)
