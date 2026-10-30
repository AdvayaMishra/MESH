"""Durable billing admission, fresh finance authority and immutable report reads."""

import hashlib
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import String, cast, func, select
from sqlalchemy.orm import Session, defer

from app.auth import Principal
from app.aws_billing import AWSBillingReport, period_bounds
from app.cloud_identity import AWSAccountIdentity
from app.core.config import settings
from app.core.db import tenant_context
from app.core.time import as_utc
from app.models import BillingCollection, IdentitySession, Membership, Organization, identifier, now
from app.services import audit, emit, lock_tenant


def binding(organization_id: str) -> tuple[AWSAccountIdentity, str]:
    role = settings().aws_billing_role_bindings.get(organization_id)
    try:
        if role is None:
            raise ValueError("Missing binding")
        identity = AWSAccountIdentity.from_role(role)
        if identity.partition != "aws":
            raise ValueError("Unsupported partition")
        return identity, hashlib.sha256(role.encode()).hexdigest()
    except ValueError:
        raise HTTPException(503, "A supported, separate AWS billing binding is required") from None


def current_authority(db: Session, p: Principal, *, write: bool = False) -> None:
    tenant_context(db, p.organization_id, p.user_id)
    permission = "finance.write" if write else "finance.read"
    p.require(permission)
    if write:
        lock_tenant(db, p.organization_id)
    member = db.scalar(
        select(Membership)
        .join(Organization, Organization.id == Membership.organization_id)
        .where(
            Membership.organization_id == p.organization_id,
            Membership.user_id == p.user_id,
            Membership.active.is_(True),
            Organization.status == "active",
        )
        .execution_options(populate_existing=True)
    )
    if member is None:
        raise HTTPException(403, "Active finance authority required")
    Principal(p.user_id, p.organization_id, member.role).require(permission)
    if settings().require_privileged_mfa and p.aal != "aal2":
        raise HTTPException(403, "MFA assurance level 2 is required")
    if member.access_not_before is not None and (
        p.issued_at is None or as_utc(p.issued_at) <= as_utc(member.access_not_before)
    ):
        raise HTTPException(401, "Sign in again after the approved access change")
    if p.session_id is None:
        if not settings().test_mode:
            raise HTTPException(401, "Active identity session required")
        return
    session = db.scalar(
        select(IdentitySession)
        .where(
            IdentitySession.user_id == p.user_id,
            IdentitySession.provider_session_id == p.session_id,
        )
        .execution_options(populate_existing=True)
    )
    if (
        session is None
        or session.revoked_at is not None
        or as_utc(session.expires_at) <= now()
        or p.expires_at is None
        or as_utc(p.expires_at) <= now()
    ):
        raise HTTPException(401, "Active identity session required")


def request_collection(
    db: Session, p: Principal, *, request_key: UUID, period: str
) -> BillingCollection:
    current_authority(db, p, write=True)
    existing = db.scalar(
        select(BillingCollection)
        .where(
            BillingCollection.organization_id == p.organization_id,
            BillingCollection.request_key == str(request_key),
        )
        .options(defer(BillingCollection.report))
    )
    if existing is not None:
        if existing.requested_by != p.user_id or existing.period != period or existing.synthetic:
            raise HTTPException(409, "Billing request key is bound to another actor or period")
        return existing
    identity, revision = binding(p.organization_id)
    try:
        period_bounds(period, now().date())
    except ValueError:
        raise HTTPException(
            422, "Billing period must be within the current twelve calendar months"
        ) from None
    daily = now().replace(hour=0, minute=0, second=0, microsecond=0)
    admitted = (
        db.scalar(
            select(func.count())
            .select_from(BillingCollection)
            .where(
                BillingCollection.organization_id == p.organization_id,
                BillingCollection.created_at >= daily,
                BillingCollection.synthetic.is_(False),
            )
        )
        or 0
    )
    pending = (
        db.scalar(
            select(func.count())
            .select_from(BillingCollection)
            .where(
                BillingCollection.organization_id == p.organization_id,
                BillingCollection.status.in_(("queued", "running")),
                BillingCollection.synthetic.is_(False),
            )
        )
        or 0
    )
    if admitted >= 20 or pending >= 3:
        raise HTTPException(429, "Billing collection admission limit reached")
    record = BillingCollection(
        id=identifier(),
        organization_id=p.organization_id,
        requested_by=p.user_id,
        requested_session_id=p.session_id,
        requested_aal=p.aal,
        request_key=str(request_key),
        period=period,
        provider_account_id=identity.account_id,
        binding_revision=revision,
        synthetic=False,
    )
    db.add(record)
    db.flush()
    emit(db, p, "finance.billing.requested", record.id)
    return record


def get_collection(
    db: Session, p: Principal, collection_id: UUID, *, write: bool = False
) -> BillingCollection:
    current_authority(db, p, write=write)
    query = (
        select(BillingCollection)
        .where(
            BillingCollection.organization_id == p.organization_id,
            BillingCollection.id == str(collection_id),
            BillingCollection.synthetic.is_(False),
        )
        .options(defer(BillingCollection.report))
    )
    if write:
        query = query.with_for_update()
    record = db.scalar(query.execution_options(populate_existing=True))
    if record is None:
        raise HTTPException(404, "Record not found")
    return record


def cancel_collection(db: Session, p: Principal, collection_id: UUID) -> BillingCollection:
    record = get_collection(db, p, collection_id, write=True)
    if record.status not in {"queued", "running"}:
        raise HTTPException(409, "Billing collection is no longer cancellable")
    record.status, record.lease_until, record.finished_at = "cancelled", None, now()
    record.error_code = "cancelled_by_owner"
    emit(db, p, "finance.billing.cancelled", record.id)
    return record


def read_report(db: Session, p: Principal, collection_id: UUID) -> AWSBillingReport:
    record = get_collection(db, p, collection_id)
    if record.status != "completed":
        raise HTTPException(409, "Billing report is not available for this collection")
    size = db.scalar(
        select(func.length(cast(BillingCollection.report, String))).where(
            BillingCollection.organization_id == p.organization_id,
            BillingCollection.id == record.id,
        )
    )
    if size is None or size > 512 * 1024:
        raise HTTPException(503, "Retained billing report is unavailable")
    raw = db.scalar(
        select(BillingCollection.report).where(
            BillingCollection.organization_id == p.organization_id,
            BillingCollection.id == record.id,
        )
    )
    try:
        report = AWSBillingReport.model_validate(raw)
        validate_report(record, report)
    except ValueError:
        raise HTTPException(503, "Retained billing report is invalid") from None
    audit(db, p, "finance.billing.report.read", record.id)
    return report


def validate_report(record: BillingCollection, report: AWSBillingReport) -> None:
    if (
        str(report.organization_id),
        report.provider_account_id,
        report.period,
        report.synthetic,
    ) != (record.organization_id, record.provider_account_id, record.period, record.synthetic):
        raise ValueError("Billing report scope mismatch")
    if (
        record.dispatched_at is None
        or report.collected_at < as_utc(record.dispatched_at)
        or report.collected_at > now()
    ):
        raise ValueError("Billing observation outside collection interval")
