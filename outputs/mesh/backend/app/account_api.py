from typing import Annotated, Literal, cast
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel, Field, SecretStr
from sqlalchemy import select

from app.api import DB, Who
from app.auth import Principal
from app.core.config import settings
from app.core.db import tenant_context
from app.identity_provider import SupabaseAuth
from app.models import Membership, Organization
from app.schemas import Input, Role
from app.services import audit, emit, lock_tenant
from app.sessions import revoke_all

router = APIRouter(prefix="/api/v1")


class OrganizationMembershipOutput(BaseModel):
    organization_id: str
    name: str
    role: Role
    verification_status: str


class OrganizationMembershipPage(BaseModel):
    items: list[OrganizationMembershipOutput]
    next_cursor: str | None = None


@router.get("/users/me/organizations", response_model=OrganizationMembershipPage)
def my_organizations(
    who: Who,
    db: DB,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    cursor: UUID | None = None,
):
    """Discover only this authenticated account's active organization memberships.

    No organization header or MFA step-up is required for this limited metadata.
    Actual organization access continues to require the existing fresh-authority
    and privileged-MFA checks. Follow next_cursor even if a page has no items.
    """
    tenant_context(db, "", who.user_id)
    query = select(Membership).where(Membership.user_id == who.user_id, Membership.active.is_(True))
    if cursor is not None:
        query = query.where(Membership.organization_id > str(cursor))
    members = db.scalars(query.order_by(Membership.organization_id).limit(limit + 1)).all()
    has_more = len(members) > limit
    selected = members[:limit]
    result = []
    for member in selected:
        tenant_context(db, member.organization_id, who.user_id)
        org = db.get(Organization, member.organization_id, populate_existing=True)
        if org is None or org.status != "active":
            continue
        result.append(
            OrganizationMembershipOutput(
                organization_id=org.id,
                name=org.name,
                role=cast(Role, member.role),
                verification_status=org.verification_status,
            )
        )
        audit(
            db,
            Principal(who.user_id, org.id, member.role),
            "organization.membership_discovered",
            org.id,
        )
    tenant_context(db, "", who.user_id)
    return OrganizationMembershipPage(
        items=result, next_cursor=selected[-1].organization_id if has_more else None
    )


class PasswordInput(Input):
    password: SecretStr = Field(min_length=12, max_length=128)


class OrganizationStatus(Input):
    status: Literal["active", "suspended"]


@router.put("/auth/password", status_code=204)
def update_password(data: PasswordInput, who: Who, db: DB, authorization: Annotated[str, Header()]):
    # Provider recovery OTP already produced the authenticated session; password remains provider-owned.
    SupabaseAuth().request(
        "user",
        {"password": data.password.get_secret_value()},
        token=authorization.split(" ", 1)[1],
        method="PUT",
    )
    revoke_all(db, who.user_id, keep=who.session_id, reason="password_changed")


@router.patch("/organizations/current/status", response_model=OrganizationStatus)
def organization_status(
    data: OrganizationStatus,
    who: Who,
    db: DB,
    organization: Annotated[UUID, Header(alias="X-Organization-ID")],
):
    org = str(organization)
    tenant_context(db, org, who.user_id)
    membership = db.get(Membership, (org, who.user_id), populate_existing=True)
    if membership is None or not membership.active or membership.role != "owner":
        raise HTTPException(403, "Active owner membership required")
    if settings().require_privileged_mfa and who.aal != "aal2":
        raise HTTPException(403, "MFA assurance level 2 required")
    record = lock_tenant(db, org)
    if record is None:
        raise HTTPException(404, "Organization not found")
    # A revocation can commit while this request waits for the tenant lock.
    # Refresh after acquiring it, then retain tenant-before-member lock order.
    membership = db.get(
        Membership, (org, who.user_id), with_for_update=True, populate_existing=True
    )
    if membership is None or not membership.active or membership.role != "owner":
        raise HTTPException(403, "Active owner membership required")
    record.status = data.status
    emit(db, Principal(who.user_id, org, "owner"), "organization." + data.status, org)
    return data
