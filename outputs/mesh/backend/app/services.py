import hashlib
import json
import secrets
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import Identity, Principal
from app.core.time import as_utc
from app.models import (
    AuditLog,
    AuditSeal,
    Invitation,
    Membership,
    Organization,
    Outbox,
    TenantRow,
    identifier,
    now,
)


def lock_tenant(db: Session, organization_id: str) -> Organization | None:
    """One lock order: tenant before existing child rows; compatible with FK key-share locks."""
    return db.scalar(
        select(Organization)
        .where(Organization.id == organization_id)
        .with_for_update(key_share=True)
    )


def scoped[T: TenantRow](
    db: Session, model: type[T], p: Principal, object_id: str, lock: bool = False
) -> T:
    query = select(model).where(model.organization_id == p.organization_id, model.id == object_id)
    if lock:
        lock_tenant(db, p.organization_id)
        query = query.with_for_update()
    record = db.scalar(query)
    if record is None:
        raise HTTPException(404, "Record not found")
    return record


def audit(db: Session, p: Principal, action: str, target: str) -> None:
    db.scalar(
        select(Organization)
        .where(Organization.id == p.organization_id)
        .with_for_update(key_share=True)
    )
    record = AuditLog(
        id=identifier(),
        organization_id=p.organization_id,
        actor_id=p.user_id,
        action=action,
        target_id=target,
    )
    db.add(record)
    db.flush()
    previous = db.scalar(
        select(AuditSeal)
        .where(AuditSeal.organization_id == p.organization_id)
        .order_by(AuditSeal.position.desc())
        .limit(1)
    )
    prior_hash = previous.digest if previous else "0" * 64
    db.add(
        AuditSeal(
            organization_id=p.organization_id,
            audit_id=record.id,
            position=previous.position + 1 if previous else 1,
            previous_hash=prior_hash,
            digest=audit_digest(record, prior_hash),
        )
    )
    db.flush()


def audit_digest(record: AuditLog, previous_hash: str) -> str:
    timestamp = (
        record.created_at.replace(tzinfo=UTC)
        if record.created_at.tzinfo is None
        else record.created_at.astimezone(UTC)
    )
    canonical = {
        "id": record.id,
        "organization_id": record.organization_id,
        "actor_id": record.actor_id,
        "action": record.action,
        "target_id": record.target_id,
        "outcome": record.outcome,
        "created_at": timestamp.isoformat(),
        "previous_hash": previous_hash,
    }
    return hashlib.sha256(
        json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def verify_audit(db: Session, p: Principal) -> dict:
    rows = db.execute(
        select(AuditSeal, AuditLog)
        .join(AuditLog, AuditLog.id == AuditSeal.audit_id)
        .where(AuditSeal.organization_id == p.organization_id)
        .order_by(AuditSeal.position)
    ).all()
    previous = "0" * 64
    valid = True
    for index, (seal, log) in enumerate(rows, start=1):
        valid = (
            valid
            and log.organization_id == p.organization_id
            and seal.position == index
            and seal.previous_hash == previous
            and secrets.compare_digest(seal.digest, audit_digest(log, previous))
        )
        previous = seal.digest
    all_ids = set(
        db.scalars(select(AuditLog.id).where(AuditLog.organization_id == p.organization_id)).all()
    )
    unsealed = len(all_ids - {log.id for _, log in rows})
    return {
        "valid": valid and unsealed == 0,
        "sealed_records": len(rows),
        "unsealed_records": unsealed,
        "head": previous,
        "external_anchor": False,
    }


def emit(db: Session, p: Principal, topic: str, target: str) -> None:
    # Never put tokens, documents, names or raw telemetry into the general event bus.
    db.add(
        Outbox(
            organization_id=p.organization_id,
            topic=topic,
            payload={"target_id": target, "version": 1},
        )
    )
    audit(db, p, topic, target)


def invitation_permission(role: str) -> str:
    if role == "hr":
        return "invite.hr"
    if role in {"senior_developer", "junior_developer", "security_analyst"}:
        return "invite.employee"
    raise HTTPException(403, "Role cannot be invited")


def invitation_issuer(
    db: Session, organization_id: str, user_id: str, role: str, *, lock: bool = False
) -> Principal | None:
    member = db.get(
        Membership, (organization_id, user_id), with_for_update=lock, populate_existing=True
    )
    if member is None or not member.active:
        return None
    fresh = Principal(member.user_id, organization_id, member.role)
    try:
        fresh.require(invitation_permission(role))
    except HTTPException:
        return None
    return fresh


def invitation_authority(db: Session, p: Principal, role: str) -> Principal:
    p.require(invitation_permission(role))
    organization = lock_tenant(db, p.organization_id)
    if organization is not None:
        db.refresh(organization, attribute_names=["status"])
    if organization is None or organization.status != "active":
        raise HTTPException(403, "Organization unavailable")
    fresh = invitation_issuer(db, p.organization_id, p.user_id, role, lock=True)
    if fresh is None:
        raise HTTPException(403, "Active invitation authority required")
    return Principal(
        fresh.user_id,
        fresh.organization_id,
        fresh.role,
        p.session_id,
        p.aal,
        p.expires_at,
        p.issued_at,
    )


def invitation(db: Session, p: Principal, email: str, role: str) -> tuple[Invitation, str]:
    p = invitation_authority(db, p, role)
    if db.scalar(
        select(Membership).where(
            Membership.organization_id == p.organization_id, Membership.email == email
        )
    ):
        raise HTTPException(409, "Membership already exists")
    token = secrets.token_urlsafe(48)
    record = Invitation(
        id=identifier(),
        organization_id=p.organization_id,
        email=email,
        role=role,
        token_hash=hashlib.sha256(token.encode()).hexdigest(),
        creator_id=p.user_id,
        expires_at=now() + timedelta(days=3),
    )
    db.add(record)
    db.flush()
    emit(db, p, "user.invited", record.id)
    return record, token


def accept_invitation(db: Session, p: Principal, who: Identity, token: str) -> Membership:
    organization = lock_tenant(db, p.organization_id)
    if organization is not None:
        db.refresh(organization, attribute_names=["status"])
    if organization is None or organization.status != "active":
        raise HTTPException(403, "Organization unavailable")
    record = db.scalar(
        select(Invitation)
        .where(
            Invitation.organization_id == p.organization_id,
            Invitation.token_hash == hashlib.sha256(token.encode()).hexdigest(),
        )
        .with_for_update()
    )
    if record is None or record.status != "pending" or as_utc(record.expires_at) <= now():
        raise HTTPException(400, "Invalid or expired invitation")
    if not secrets.compare_digest(record.email, who.email):
        raise HTTPException(403, "Invitation belongs to another identity")
    if invitation_issuer(db, p.organization_id, record.creator_id, record.role, lock=True) is None:
        raise HTTPException(400, "Invitation is no longer authorized; request a new invitation")
    if db.get(Membership, (p.organization_id, who.user_id)):
        raise HTTPException(409, "Membership already exists")
    membership = Membership(
        organization_id=p.organization_id, user_id=who.user_id, email=who.email, role=record.role
    )
    db.add(membership)
    record.status = "accepted"
    record.accepted_at = datetime.now(UTC)
    emit(db, p, "invitation.accepted", record.id)
    return membership


def payroll_net(gross: Decimal, deductions: Decimal) -> Decimal:
    if not gross.is_finite() or not deductions.is_finite() or deductions < 0 or gross < deductions:
        raise HTTPException(422, "Deductions must be between zero and gross")
    return (gross - deductions).quantize(Decimal("0.01"))
