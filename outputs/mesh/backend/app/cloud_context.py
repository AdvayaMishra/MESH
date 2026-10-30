"""R4-owned, read-only cloud context facade. Reads never invoke cloud providers."""

from datetime import UTC, datetime
from functools import wraps
from typing import Annotated, Literal
from uuid import UUID

from fastapi import HTTPException
from pydantic import AwareDatetime, Field, TypeAdapter, ValidationError
from sqlalchemy import String, cast, func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.auth import Principal
from app.cloud_context_schema import (
    MAX_PAGE_BYTES,
    MAX_SNAPSHOT_BYTES,
    Code,
    Envelope,
    EvidenceObservation,
    Scope,
    Snapshot,
    Text,
    Wire,
    freshness,
    wire_bytes,
)
from app.core.config import settings
from app.core.db import tenant_context
from app.core.time import as_utc
from app.models import CloudAssessment, IdentitySession, Membership, Organization, now
from app.services import audit


class ContextSelection(Wire):
    contract: Literal["mesh.cloud-context"] = "mesh.cloud-context"
    schema_version: Literal["1.0.0"] = "1.0.0"
    as_of: AwareDatetime
    state: Literal["available", "partial", "stale", "unavailable"]
    envelope: Envelope | None
    reasons: Annotated[list[Code], Field(max_length=20)]


class Page(Wire):
    contract: Literal["mesh.cloud-context"] = "mesh.cloud-context"
    schema_version: Literal["1.0.0"] = "1.0.0"
    assessment_id: UUID
    items: list[dict]
    total: int
    limit: int
    offset: int
    next_offset: int | None


class Reference(Wire):
    scope: Scope
    node_type: Code
    identity_kind: Literal["provider_uid", "arn", "scoped_native_id"]
    provider_identity: Annotated[str, Field(min_length=1, max_length=2048)]


class Resolution(Wire):
    reference: Reference
    state: Literal["matched", "ambiguous", "not_found", "unknown"]
    candidate_keys: Annotated[list[Text], Field(max_length=100)]
    reasons: Annotated[list[Code], Field(max_length=20)]
    # Retain immutable times/evidence in the candidate observation; consumer uses its explicit cutoff.
    candidates: Annotated[list[dict], Field(max_length=100)]


def boundary(function):
    @wraps(function)
    def call(*args, **kwargs):
        try:
            return function(*args, **kwargs)
        except SQLAlchemyError:
            raise HTTPException(503, "Cloud context storage is unavailable") from None
        except ValidationError:
            raise HTTPException(422, "Invalid cloud context input") from None

    return call


def authorize(db: Session, principal: Principal):
    tenant_context(db, principal.organization_id, principal.user_id)
    principal.require("security.read")
    member = db.scalar(
        select(Membership)
        .join(Organization, Membership.organization_id == Organization.id)
        .where(
            Membership.organization_id == principal.organization_id,
            Membership.user_id == principal.user_id,
            Membership.active.is_(True),
            Organization.status == "active",
        )
        .execution_options(populate_existing=True)
    )
    if member is None:
        raise HTTPException(403, "Active organization membership required")
    Principal(member.user_id, principal.organization_id, member.role).require("security.read")
    if settings().require_privileged_mfa and principal.aal != "aal2":
        raise HTTPException(403, "MFA assurance level 2 is required for privileged access")
    if member.access_not_before is not None and (
        principal.issued_at is None
        or as_utc(principal.issued_at) <= as_utc(member.access_not_before)
    ):
        raise HTTPException(401, "Sign in again after the approved access change")
    if principal.session_id is not None:
        session = db.scalar(
            select(IdentitySession)
            .where(
                IdentitySession.user_id == principal.user_id,
                IdentitySession.provider_session_id == principal.session_id,
            )
            .execution_options(populate_existing=True)
        )
        if (
            session is None
            or session.revoked_at is not None
            or as_utc(session.expires_at) <= now()
            or principal.expires_at is None
            or as_utc(principal.expires_at) <= now()
        ):
            raise HTTPException(401, "Active identity session required")
    elif not settings().test_mode:
        raise HTTPException(401, "Active identity session required")


def assessment_uuid(value) -> str:
    try:
        return str(UUID(str(value)))
    except (ValueError, TypeError, AttributeError):
        raise HTTPException(422, "Invalid assessment identifier") from None


def load(db, principal, assessment_id) -> Snapshot | None:
    key = assessment_uuid(assessment_id)
    size = db.execute(
        select(
            CloudAssessment.id, func.length(cast(CloudAssessment.normalized_context, String))
        ).where(
            CloudAssessment.organization_id == principal.organization_id, CloudAssessment.id == key
        )
    ).first()
    if size is None:
        raise HTTPException(404, "Record not found")
    if size[1] is None:
        return None
    if size[1] > MAX_SNAPSHOT_BYTES:
        raise HTTPException(503, "Cloud context exceeds retained size limit")
    data = db.scalar(
        select(CloudAssessment.normalized_context).where(
            CloudAssessment.organization_id == principal.organization_id, CloudAssessment.id == key
        )
    )
    if data is None:
        return None
    envelope = data.get("envelope", {}) if isinstance(data, dict) else {}
    if envelope.get("schema_version") != "1.0.0" or envelope.get("publication_state") != "sealed":
        raise HTTPException(409, "Cloud context version or publication state is incompatible")
    try:
        snapshot = Snapshot.model_validate(data)
        if (
            str(snapshot.envelope.organization_id) != principal.organization_id
            or str(snapshot.envelope.assessment_id) != key
        ):
            raise ValueError("Stored scope mismatch")
        return snapshot
    except ValueError:
        raise HTTPException(503, "Retained cloud context is invalid") from None


def same_scope(envelope: Envelope, scope: Scope) -> bool:
    return (
        envelope.scope == scope
        if scope.scope_kind == "account"
        else scope in envelope.requested_scopes
    )


def observed_by(snapshot, cutoff):
    return snapshot.envelope.collected_at <= cutoff and all(
        item.timestamps.observed_at is None or item.timestamps.observed_at <= cutoff
        for item in [
            *snapshot.assets,
            *snapshot.principals,
            *snapshot.permissions,
            *snapshot.relationships,
        ]
    )


@boundary
def get_context(
    db: Session,
    principal: Principal,
    *,
    scope: Scope | dict,
    as_of: datetime,
    assessment_id=None,
    synthetic: bool = False,
) -> ContextSelection:
    authorize(db, principal)
    scope = Scope.model_validate(scope)
    cutoff = TypeAdapter(AwareDatetime).validate_python(as_of).astimezone(UTC)
    if type(synthetic) is not bool:
        raise HTTPException(422, "Synthetic selector must be boolean")
    if str(scope.organization_id) != principal.organization_id:
        raise HTTPException(404, "Record not found")
    snapshot = None
    if assessment_id is not None:
        snapshot = load(db, principal, assessment_id)
        if snapshot is not None and (
            not same_scope(snapshot.envelope, scope) or snapshot.envelope.synthetic != synthetic
        ):
            raise HTTPException(404, "Record not found")
        if snapshot is not None and not observed_by(snapshot, cutoff):
            snapshot = None
    else:
        env = CloudAssessment.normalized_context["envelope"]
        ids = db.scalars(
            select(CloudAssessment.id)
            .where(
                CloudAssessment.organization_id == principal.organization_id,
                env["scope"]["partition"].as_string() == scope.partition,
                env["scope"]["provider_account_id"].as_string() == scope.provider_account_id,
                env["synthetic"].as_boolean() == synthetic,
                env["collected_at"].as_string() <= cutoff.isoformat().replace("+00:00", "Z"),
            )
            .order_by(env["collected_at"].as_string().desc(), CloudAssessment.id.desc())
            .limit(1001)
        ).all()
        for index, key in enumerate(ids):
            if index == 1000:
                raise HTTPException(503, "Cloud context selection exceeds bounded search")
            candidate = load(db, principal, key)
            if (
                candidate is not None
                and same_scope(candidate.envelope, scope)
                and observed_by(candidate, cutoff)
            ):
                snapshot = candidate
                break
    audit(
        db,
        principal,
        "security.cloud.context.read",
        str(snapshot.envelope.assessment_id) if snapshot else "unavailable",
    )
    if snapshot is None:
        return ContextSelection(
            as_of=cutoff,
            state="unavailable",
            envelope=None,
            reasons=["legacy_metadata_missing" if assessment_id is not None else "not_collected"],
        )
    relevant = [
        item
        for item in snapshot.envelope.coverage
        if scope.scope_kind == "account" or item.scope == scope
    ]
    ages = [freshness(item.timestamps, cutoff) for item in relevant]
    stale = "stale" in ages
    unknown = not ages or "unknown" in ages
    return ContextSelection(
        as_of=cutoff,
        state="stale"
        if stale
        else "partial"
        if snapshot.envelope.partial or unknown
        else "available",
        envelope=snapshot.envelope,
        reasons=["stale"]
        if stale
        else ["clock_uncertain"]
        if unknown
        else ["not_collected"]
        if snapshot.envelope.partial
        else [],
    )


def page(db, principal, *, assessment_id, collection, order_key, limit, offset):
    authorize(db, principal)
    if (
        type(limit) is not int
        or type(offset) is not int
        or not 1 <= limit <= 100
        or not 0 <= offset <= 100000
    ):
        raise HTTPException(422, "Invalid cloud context page bounds")
    snapshot = load(db, principal, assessment_id)
    if snapshot is None:
        raise HTTPException(409, "Legacy assessment has no normalized cloud context")
    rows = sorted(getattr(snapshot, collection), key=lambda row: str(getattr(row, order_key)))
    output = Page(
        assessment_id=assessment_id,
        items=[],
        total=len(rows),
        limit=limit,
        offset=offset,
        next_offset=None,
    )
    for record in rows[offset : offset + limit]:
        item = record.model_dump(mode="json", by_alias=True)
        output.items.append(item)
        output.next_offset = (
            offset + len(output.items) if offset + len(output.items) < len(rows) else None
        )
        if wire_bytes(output) > MAX_PAGE_BYTES:
            output.items.pop()
            if not output.items:
                raise HTTPException(503, "Cloud context record exceeds page byte limit")
            output.next_offset = offset + len(output.items)
            break
    audit(
        db, principal, "security.cloud.context." + collection, str(snapshot.envelope.assessment_id)
    )
    return output


@boundary
def list_assets(db, principal, *, assessment_id, limit=50, offset=0):
    return page(
        db,
        principal,
        assessment_id=assessment_id,
        collection="assets",
        order_key="asset_key",
        limit=limit,
        offset=offset,
    )


@boundary
def list_principals(db, principal, *, assessment_id, limit=50, offset=0):
    return page(
        db,
        principal,
        assessment_id=assessment_id,
        collection="principals",
        order_key="principal_key",
        limit=limit,
        offset=offset,
    )


@boundary
def list_permissions(db, principal, *, assessment_id, limit=50, offset=0):
    return page(
        db,
        principal,
        assessment_id=assessment_id,
        collection="permissions",
        order_key="permission_id",
        limit=limit,
        offset=offset,
    )


@boundary
def list_relationships(db, principal, *, assessment_id, limit=50, offset=0):
    return page(
        db,
        principal,
        assessment_id=assessment_id,
        collection="relationships",
        order_key="relationship_id",
        limit=limit,
        offset=offset,
    )


@boundary
def get_evidence(db, principal, *, assessment_id, evidence_id) -> EvidenceObservation:
    authorize(db, principal)
    snapshot = load(db, principal, assessment_id)
    key = assessment_uuid(evidence_id)
    record = (
        next((item for item in snapshot.evidence if str(item.reference.evidence_id) == key), None)
        if snapshot
        else None
    )
    if record is None:
        raise HTTPException(404, "Record not found")
    if wire_bytes(record) > MAX_PAGE_BYTES:
        raise HTTPException(503, "Cloud evidence exceeds byte limit")
    audit(db, principal, "security.cloud.context.evidence", key)
    return record


@boundary
def resolve_references(db, principal, *, assessment_id, references) -> list[Resolution]:
    authorize(db, principal)
    if not isinstance(references, list) or len(references) > 100:
        raise HTTPException(422, "Cloud reference count exceeds bound")
    references = TypeAdapter(list[Reference]).validate_python(references)
    if len(references) > 100:
        raise HTTPException(422, "Cloud reference count exceeds bound")
    snapshot = load(db, principal, assessment_id)
    if snapshot is None:
        raise HTTPException(409, "Legacy assessment has no normalized cloud context")
    nodes = [*snapshot.assets, *snapshot.principals]
    results = []
    for reference in references:
        if str(reference.scope.organization_id) != principal.organization_id:
            raise HTTPException(404, "Record not found")
        field = {"provider_uid": "provider_uid", "arn": "arn", "scoped_native_id": "native_id"}[
            reference.identity_kind
        ]
        matches = [
            node
            for node in nodes
            if node.scope == reference.scope
            and node.node_type == reference.node_type
            and getattr(node, field) == reference.provider_identity
        ]
        coverage = [
            entry
            for entry in snapshot.envelope.coverage
            if entry.scope == reference.scope
            and entry.check == reference.scope.service + ".inventory"
        ]
        evidenced = [
            node
            for node in matches
            if all(
                any(
                    evidence.reference == ref and evidence.availability == "available"
                    for evidence in snapshot.evidence
                )
                for ref in node.evidence_refs
            )
        ]
        if len(matches) > 100:
            raise HTTPException(503, "Cloud reference ambiguity exceeds bound")
        complete = bool(coverage) and all(
            entry.state == "complete" and not entry.truncated for entry in coverage
        )
        state: Literal["matched", "ambiguous", "not_found", "unknown"] = (
            "matched"
            if len(matches) == len(evidenced) == 1
            else "ambiguous"
            if len(evidenced) > 1
            else "not_found"
            if not matches and complete
            else "unknown"
        )
        candidates = [node.model_dump(mode="json", by_alias=True) for node in evidenced]
        keys = [str(item.get("asset_key", item.get("principal_key"))) for item in candidates]
        results.append(
            Resolution(
                reference=reference,
                state=state,
                candidate_keys=keys,
                reasons=[]
                if state == "matched"
                else ["identity_unresolved"]
                if state in {"unknown", "ambiguous"}
                else [],
                candidates=candidates,
            )
        )
    if wire_bytes({"results": [item.model_dump(mode="json") for item in results]}) > MAX_PAGE_BYTES:
        raise HTTPException(503, "Cloud reference resolution exceeds byte limit")
    audit(db, principal, "security.cloud.context.resolve", str(snapshot.envelope.assessment_id))
    return results
