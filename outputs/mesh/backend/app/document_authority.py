"""Fresh document authority after the tenant lock, before content access or mutation."""

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import Principal
from app.core.config import settings
from app.core.time import as_utc
from app.models import Employee, IdentitySession, Membership, now
from app.services import lock_tenant, scoped


def authority(db: Session, p: Principal, *, hr: bool = True) -> None:
    if hr:
        p.require("employee.write")
    organization = lock_tenant(db, p.organization_id)
    if organization is not None:
        db.refresh(organization, attribute_names=["status"])
    member = db.scalar(
        select(Membership)
        .where(
            Membership.organization_id == p.organization_id,
            Membership.user_id == p.user_id,
            Membership.active.is_(True),
        )
        .execution_options(populate_existing=True)
    )
    if (
        organization is None
        or organization.status != "active"
        or member is None
        or (hr and member.role != "hr")
    ):
        raise HTTPException(403, "Active document authority required")
    if (
        settings().require_privileged_mfa
        and member.role in {"owner", "hr", "security_analyst"}
        and p.aal != "aal2"
    ):
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


def upload_authority(db: Session, p: Principal, employee_id: str) -> None:
    authority(db, p, hr=False)
    employee = scoped(db, Employee, p, employee_id, lock=True)
    db.refresh(employee, attribute_names=["user_id", "status"])
    if employee.user_id != p.user_id or employee.status not in {"onboarding", "active"}:
        raise HTTPException(403, "Active employee ownership required for document upload")
