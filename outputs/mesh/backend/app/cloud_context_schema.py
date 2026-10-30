"""Bounded wire models for mesh.cloud-context 1.0.0 (R4-owned)."""

import json
from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictFloat,
    StrictInt,
    StrictStr,
    field_validator,
    model_validator,
)

from app.cloud_keys import cloud_node_key

MAX_SNAPSHOT_BYTES = 8 * 1024 * 1024
MAX_PAGE_BYTES = 512 * 1024
Text = Annotated[str, Field(min_length=1, max_length=256)]
Code = Annotated[str, Field(pattern=r"^[a-z0-9_.-]{1,64}$")]
Account = Annotated[str, Field(pattern=r"^[0-9]{12}$")]
Digest = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
Primitive = StrictBool | StrictInt | StrictFloat | StrictStr | None


class Wire(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    @field_validator("*", mode="after")
    @classmethod
    def utc_times(cls, value):
        return value.astimezone(UTC) if isinstance(value, datetime) else value


class Scope(Wire):
    organization_id: UUID
    provider: Literal["aws"] = "aws"
    partition: Literal["aws", "aws-us-gov", "aws-cn"]
    provider_account_id: Account
    service: Code
    scope_kind: Literal["account", "global", "regional"]
    region: Annotated[str, Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)+$", max_length=64)] | None

    @model_validator(mode="after")
    def valid_scope(self) -> Self:
        if self.scope_kind == "account" and self.service != "account":
            raise ValueError("Account envelope requires account service")
        if self.service == "account" and self.scope_kind != "account":
            raise ValueError("Account service requires account scope")
        if (self.scope_kind == "regional") != (self.region is not None):
            raise ValueError("Region must match scope kind")
        return self


class Times(Wire):
    observed_at: AwareDatetime | None
    provider_modified_at: AwareDatetime | None = None
    collected_at: AwareDatetime
    fresh_until: AwareDatetime | None
    max_age_seconds: Annotated[int, Field(strict=True, ge=1, le=86400)] = 3600
    freshness_policy_version: Literal["1"] = "1"

    @model_validator(mode="after")
    def valid_times(self) -> Self:
        if self.observed_at is None:
            if self.fresh_until is not None:
                raise ValueError("Unknown observation cannot have expiry")
        elif (
            self.observed_at > self.collected_at
            or self.fresh_until != self.observed_at + timedelta(seconds=self.max_age_seconds)
        ):
            raise ValueError("Invalid observation interval or expiry")
        return self


class EvidenceRef(Wire):
    organization_id: UUID
    assessment_id: UUID
    evidence_id: UUID
    source_kind: Literal[
        "provider_response",
        "policy_statement",
        "legacy_finding",
        "provider_audit_event",
        "synthetic_fixture",
    ]
    operation: Code
    observed_at: AwareDatetime | None
    content_digest: Digest | None
    verification: Literal[
        "provider_observed", "reported_unverified", "synthetic_fixture", "legacy_unverified"
    ]


class EvidenceObservation(Wire):
    reference: EvidenceRef
    availability: Literal["available", "expired", "unavailable"]
    summary: Annotated[dict[Code, Primitive], Field(max_length=32)] | None
    reasons: Annotated[list[Code], Field(max_length=20)] = []

    @field_validator("summary")
    @classmethod
    def safe_summary(cls, value):
        allowed = {
            "node_type",
            "native_id",
            "arn",
            "provider_uid",
            "policy_arn",
            "statement_index",
            "effect",
            "condition_state",
            "storage_encrypted",
            "reported_publicly_accessible",
            "root_access_keys_present",
            "root_console_enabled",
            "root_mfa_enabled",
        }
        if value is not None and (
            set(value) - allowed
            or any(isinstance(item, str) and len(item) > 2048 for item in value.values())
        ):
            raise ValueError("Unsupported evidence summary")
        return value

    @model_validator(mode="after")
    def availability_content(self) -> Self:
        if (self.availability == "available") != (self.summary is not None):
            raise ValueError("Evidence content must match availability")
        return self


class Fact(Wire):
    value: Primitive
    state: Literal["known", "unknown", "not_applicable"]
    evidence_refs: Annotated[list[EvidenceRef], Field(max_length=20)]
    reason_code: Code | None = None

    @model_validator(mode="after")
    def consistent_fact(self) -> Self:
        if self.state == "known" and (self.value is None or not self.evidence_refs):
            raise ValueError("Known fact requires observed value and evidence")
        if self.state != "known" and self.value is not None:
            raise ValueError("Unknown fact cannot carry a known value")
        if isinstance(self.value, str) and len(self.value) > 256:
            raise ValueError("Fact text exceeds bound")
        return self


class Node(Wire):
    organization_id: UUID
    assessment_id: UUID
    node_type: Code
    scope: Scope
    ownership: Literal["bound_account", "external_account", "aws_managed", "aws_service", "unknown"]
    owner_account_id: Account | None
    identity_kind: Literal["provider_uid", "arn", "scoped_native_id"]
    identity_strength: Literal["provider_uid", "scoped_reference"]
    provider_uid: Text | None
    arn: Annotated[str, Field(min_length=1, max_length=2048)] | None
    native_id: Text | None
    incarnation_ref: Text | None
    display_name: Text | None
    lifecycle_state: Literal["observed_present", "observed_deleted", "unknown"]
    timestamps: Times
    facts: Annotated[dict[Code, Fact], Field(max_length=32)]
    evidence_refs: Annotated[list[EvidenceRef], Field(min_length=1, max_length=20)]

    @model_validator(mode="after")
    def identity_valid(self) -> Self:
        if self.scope.organization_id != self.organization_id:
            raise ValueError("Node scope crosses tenant")
        if (
            self.ownership in {"bound_account", "external_account"}
            and self.owner_account_id is None
        ):
            raise ValueError("Account ownership requires an account")
        if (
            self.ownership == "bound_account"
            and self.owner_account_id != self.scope.provider_account_id
        ):
            raise ValueError("Bound ownership account mismatch")
        if (
            self.ownership == "external_account"
            and self.owner_account_id == self.scope.provider_account_id
        ):
            raise ValueError("External ownership must identify another account")
        if (
            self.ownership in {"unknown", "aws_managed", "aws_service"}
            and self.owner_account_id is not None
        ):
            raise ValueError("Non-account ownership cannot invent an account")
        if (self.identity_kind == "provider_uid") != (self.identity_strength == "provider_uid"):
            raise ValueError("Identity strength must match identity kind")
        if self.provider_uid is not None and self.identity_kind != "provider_uid":
            raise ValueError("Use strongest retained provider identity")
        if set(self.facts) - {
            "storage_encrypted",
            "reported_publicly_accessible",
            "root_access_keys_present",
            "root_console_enabled",
            "root_mfa_enabled",
            "console_mfa_present",
            "active_key_over_age_policy",
        }:
            raise ValueError("Unsupported cloud fact")
        if self.arn is not None:
            namespace = self.owner_account_id or {
                "aws_managed": "aws-managed",
                "aws_service": "aws-service",
                "unknown": "unknown:" + self.scope.provider_account_id,
            }.get(self.ownership, "")
            cloud_node_key(
                organization_id=str(self.organization_id),
                partition=self.scope.partition,
                owner_namespace=namespace,
                service=self.scope.service,
                region=self.scope.region,
                node_type=self.node_type,
                identity_kind="arn",
                provider_identity=self.arn,
            )
        return self

    def expected_key(self) -> str:
        namespace = self.owner_account_id or {
            "aws_managed": "aws-managed",
            "aws_service": "aws-service",
            "unknown": "unknown:" + self.scope.provider_account_id,
        }.get(self.ownership, "")
        value = {
            "provider_uid": self.provider_uid,
            "arn": self.arn,
            "scoped_native_id": self.native_id,
        }[self.identity_kind]
        if value is None:
            raise ValueError("Missing selected provider identity")
        return cloud_node_key(
            organization_id=str(self.organization_id),
            partition=self.scope.partition,
            owner_namespace=namespace,
            service=self.scope.service,
            region=self.scope.region,
            node_type=self.node_type,
            identity_kind=self.identity_kind,
            provider_identity=value,
        )


class Asset(Node):
    asset_key: Annotated[str, Field(pattern=r"^ca1_[a-f0-9]{64}$")]

    @model_validator(mode="after")
    def valid_key(self) -> Self:
        if self.asset_key != self.expected_key():
            raise ValueError("Asset key does not match retained identity tuple")
        return self


class CloudPrincipal(Node):
    principal_key: Annotated[str, Field(pattern=r"^cp1_[a-f0-9]{64}$")]
    principal_type: Literal[
        "iam_user",
        "iam_role",
        "assumed_role_session",
        "account_root",
        "federated_principal",
        "service_principal",
        "external_reference",
        "unknown",
    ]

    @model_validator(mode="after")
    def valid_key(self) -> Self:
        if self.principal_key != self.expected_key():
            raise ValueError("Principal key does not match retained identity tuple")
        return self


class NodeRef(Wire):
    kind: Literal["asset", "principal"]
    key: Annotated[str, Field(pattern=r"^(ca1|cp1)_[a-f0-9]{64}$")]

    @model_validator(mode="after")
    def correct_prefix(self) -> Self:
        if self.key.startswith("ca1_") != (self.kind == "asset"):
            raise ValueError("Reference kind/key mismatch")
        return self


Selectors = Annotated[
    list[Annotated[str, Field(min_length=1, max_length=2048)]], Field(max_length=1000)
]


class PermissionObservation(Wire):
    organization_id: UUID
    assessment_id: UUID
    permission_id: UUID
    subject_ref: NodeRef | None
    principal_key: Annotated[str, Field(pattern=r"^cp1_[a-f0-9]{64}$")] | None
    policy_arn: Annotated[str, Field(max_length=2048)] | None
    policy_version_ref: Text | None
    statement_index: Annotated[int, Field(strict=True, ge=0)]
    policy_kind: Literal[
        "identity_managed",
        "identity_inline",
        "resource",
        "trust",
        "permissions_boundary",
        "session",
        "scp",
        "rcp",
        "acl",
        "unknown",
    ]
    observed_effect: Literal["Allow", "Deny"]
    actions: Selectors
    not_actions: Selectors
    resources: Selectors
    not_resources: Selectors
    condition_state: Literal["absent", "present", "unknown"]
    condition_digest: Digest | None
    evaluation_basis: Literal["observed_statement_only"] = "observed_statement_only"
    effective_decision: Literal["not_evaluated", "unknown"] = "not_evaluated"
    unknown_dependencies: Annotated[list[Code], Field(max_length=32)]
    timestamps: Times
    evidence_refs: Annotated[list[EvidenceRef], Field(min_length=1, max_length=20)]

    @model_validator(mode="after")
    def statement_semantics(self) -> Self:
        if bool(self.actions) == bool(self.not_actions) or (self.resources and self.not_resources):
            raise ValueError("Statement selector alternatives must remain exclusive")
        if self.policy_kind != "trust" and not (self.resources or self.not_resources):
            raise ValueError("Permission requires exact resource selectors")
        if self.principal_key is not None and (
            self.subject_ref is None
            or self.subject_ref.kind != "principal"
            or self.subject_ref.key != self.principal_key
        ):
            raise ValueError("Permission principal/subject mismatch")
        if (self.condition_state == "present") != (self.condition_digest is not None):
            raise ValueError("Present condition requires retained digest")
        return self


class Relationship(Wire):
    organization_id: UUID
    assessment_id: UUID
    relationship_id: UUID
    from_: NodeRef = Field(alias="from")
    to: NodeRef
    relationship_type: Literal[
        "member_of",
        "policy_attached",
        "trusts_principal",
        "session_of_role",
        "resource_policy_references",
        "policy_may_allow",
        "policy_explicit_deny",
        "boundary_attached",
        "network_group_attached",
    ]
    basis: Literal[
        "provider_observed", "policy_derived", "reported_unverified", "synthetic_fixture"
    ]
    resolution: Literal["resolved", "external_reference", "unresolved"]
    condition_state: Literal["absent", "present", "unknown"]
    effective_decision: Literal["not_evaluated", "unknown"] = "not_evaluated"
    timestamps: Times
    evidence_refs: Annotated[list[EvidenceRef], Field(min_length=1, max_length=20)]


class Coverage(Wire):
    scope: Scope
    check: Code
    state: Literal[
        "complete", "partial", "denied", "unsupported", "not_requested", "failed", "unknown"
    ]
    timestamps: Times
    observed_count: Annotated[int, Field(strict=True, ge=0)]
    expected_total: Annotated[int, Field(strict=True, ge=0)] | None
    configured_limit: Annotated[int, Field(strict=True, ge=1)]
    truncated: StrictBool
    reason_code: Code | None

    @model_validator(mode="after")
    def truthful_complete(self) -> Self:
        if self.state == "complete" and (
            self.truncated
            or (self.expected_total is not None and self.expected_total != self.observed_count)
        ):
            raise ValueError("Truncated inventory cannot be complete")
        return self


class Envelope(Wire):
    contract: Literal["mesh.cloud-context"] = "mesh.cloud-context"
    schema_version: Literal["1.0.0"] = "1.0.0"
    identity_version: Literal["mesh-cloud-identity-v1"] = "mesh-cloud-identity-v1"
    organization_id: UUID
    assessment_id: UUID
    source_job_id: UUID | None
    scope: Scope
    requested_scopes: Annotated[list[Scope], Field(min_length=1, max_length=20)]
    binding_ref: Text
    binding_revision: Digest
    normalizer_version: Text
    collector_version: Text
    publication_state: Literal["sealed"] = "sealed"
    synthetic: StrictBool
    provenance: Literal["provider_observed", "synthetic_fixture"]
    collection_started_at: AwareDatetime
    collection_finished_at: AwareDatetime
    collected_at: AwareDatetime
    coverage: Annotated[list[Coverage], Field(min_length=1, max_length=100)]
    partial: StrictBool
    limits: Annotated[dict[Code, Annotated[int, Field(strict=True, ge=1)]], Field(max_length=20)]
    errors: Annotated[list[Code], Field(max_length=1000)]
    limitations: Annotated[list[Text], Field(min_length=1, max_length=20)]

    @model_validator(mode="after")
    def coherent_envelope(self) -> Self:
        if not self.collection_started_at <= self.collection_finished_at <= self.collected_at:
            raise ValueError("Collection timestamps are inconsistent")
        if self.scope.scope_kind != "account" or self.scope.organization_id != self.organization_id:
            raise ValueError("Invalid account envelope")
        if self.synthetic != (self.provenance == "synthetic_fixture"):
            raise ValueError("Synthetic provenance mismatch")
        if not self.partial and (
            self.errors
            or any(entry.state != "complete" or entry.truncated for entry in self.coverage)
        ):
            raise ValueError("Incomplete coverage cannot produce a complete snapshot")
        for scope in [*self.requested_scopes, *(entry.scope for entry in self.coverage)]:
            if (
                scope.organization_id,
                scope.provider,
                scope.partition,
                scope.provider_account_id,
            ) != (
                self.organization_id,
                self.scope.provider,
                self.scope.partition,
                self.scope.provider_account_id,
            ):
                raise ValueError("Snapshot scope crosses tenant/account")
        return self


class Snapshot(Wire):
    envelope: Envelope
    assets: Annotated[list[Asset], Field(max_length=10000)]
    principals: Annotated[list[CloudPrincipal], Field(max_length=10000)]
    permissions: Annotated[list[PermissionObservation], Field(max_length=10000)]
    relationships: Annotated[list[Relationship], Field(max_length=50000)]
    evidence: Annotated[list[EvidenceObservation], Field(max_length=20000)]

    @model_validator(mode="after")
    def closed_snapshot(self) -> Self:
        envelope = self.envelope
        if len(self.assets) + len(self.principals) > 10000:
            raise ValueError("Snapshot node bound exceeded")
        nodes = {item.asset_key: item for item in self.assets} | {
            item.principal_key: item for item in self.principals
        }
        if len(nodes) != len(self.assets) + len(self.principals):
            raise ValueError("Duplicate node identity")
        refs = {item.reference.evidence_id: item.reference for item in self.evidence}
        if len(refs) != len(self.evidence):
            raise ValueError("Duplicate evidence identity")
        requested = [scope.model_dump() for scope in envelope.requested_scopes]
        records: list[Asset | CloudPrincipal | PermissionObservation | Relationship] = [
            *self.assets,
            *self.principals,
            *self.permissions,
            *self.relationships,
        ]
        for item in records:
            if (item.organization_id, item.assessment_id) != (
                envelope.organization_id,
                envelope.assessment_id,
            ):
                raise ValueError("Cross-snapshot record")
            if item.timestamps.collected_at > envelope.collected_at or (
                item.timestamps.observed_at is not None
                and item.timestamps.observed_at < envelope.collection_started_at
            ):
                raise ValueError("Record observation outside collection interval")
            for ref in item.evidence_refs:
                if refs.get(ref.evidence_id) != ref:
                    raise ValueError("Dangling evidence reference")
        for node in [*self.assets, *self.principals]:
            if node.scope.model_dump() not in requested:
                raise ValueError("Node outside requested scope")
            for fact in node.facts.values():
                for ref in fact.evidence_refs:
                    if refs.get(ref.evidence_id) != ref:
                        raise ValueError("Dangling fact evidence")
        for evidence in self.evidence:
            ref = evidence.reference
            if (ref.organization_id, ref.assessment_id) != (
                envelope.organization_id,
                envelope.assessment_id,
            ):
                raise ValueError("Cross-snapshot evidence")
            if (ref.verification == "synthetic_fixture") != envelope.synthetic:
                raise ValueError("Mixed synthetic and provider evidence")
            if (
                ref.observed_at is not None
                and not envelope.collection_started_at <= ref.observed_at <= envelope.collected_at
            ):
                raise ValueError("Evidence time outside collection")
        for coverage in envelope.coverage:
            if (
                coverage.scope.model_dump() not in requested
                or coverage.timestamps.collected_at > envelope.collected_at
            ):
                raise ValueError("Coverage outside requested scope/interval")
        for group in (self.permissions, self.relationships):
            ids = [
                item.permission_id
                if isinstance(item, PermissionObservation)
                else item.relationship_id
                for item in group
            ]
            if len(set(ids)) != len(ids):
                raise ValueError("Duplicate record ID")
        for item in self.permissions:
            if item.subject_ref is not None and item.subject_ref.key not in nodes:
                raise ValueError("Dangling permission subject")
        for edge in self.relationships:
            if edge.from_.key not in nodes or edge.to.key not in nodes:
                raise ValueError("Dangling relationship endpoint")
            source, target = nodes[edge.from_.key], nodes[edge.to.key]
            valid = {
                "member_of": source.node_type == "iam.user" and target.node_type == "iam.group",
                "policy_attached": target.node_type == "iam.policy",
                "trusts_principal": source.node_type == "iam.role"
                and isinstance(target, CloudPrincipal),
                "session_of_role": source.node_type == "sts.assumed_role_session"
                and target.node_type == "iam.role",
                "resource_policy_references": isinstance(source, Asset)
                and isinstance(target, CloudPrincipal),
                "policy_may_allow": isinstance(target, Asset),
                "policy_explicit_deny": isinstance(target, Asset),
                "boundary_attached": isinstance(source, CloudPrincipal)
                and target.node_type == "iam.policy",
                "network_group_attached": isinstance(source, Asset)
                and target.node_type == "ec2.security_group",
            }[edge.relationship_type]
            if not valid:
                raise ValueError("Relationship endpoints violate declared semantics")
        if len(self.model_dump_json(by_alias=True).encode()) > MAX_SNAPSHOT_BYTES:
            raise ValueError("Snapshot byte bound exceeded")
        return self


def wire_bytes(value: Wire | dict) -> int:
    data = value.model_dump(mode="json", by_alias=True) if isinstance(value, Wire) else value
    return len(
        json.dumps(data, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")
    )


def freshness(times: Times, as_of: datetime) -> Literal["fresh", "stale", "unknown"]:
    if times.observed_at is None or times.fresh_until is None or times.observed_at > as_of:
        return "unknown"
    return "fresh" if times.fresh_until > as_of else "stale"
