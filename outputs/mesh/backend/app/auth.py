from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

import jwt
from fastapi import Depends, Header, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt.exceptions import PyJWKClientConnectionError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.db import session, tenant_context
from app.core.time import as_utc
from app.models import Membership, Organization

bearer = HTTPBearer(auto_error=False)

PERMISSIONS: dict[str, frozenset[str]] = {
    "owner": frozenset(
        {
            "organization.manage",
            "invite.hr",
            "project.read",
            "project.approve",
            "finance.read",
            "finance.write",
            "security.summary",
            "audit.read",
            "trust.review",
        }
    ),
    "hr": frozenset(
        {
            "employee.read",
            "employee.write",
            "invite.employee",
            "payroll.read",
            "payroll.write",
            "trust.review",
        }
    ),
    "senior_developer": frozenset(
        {
            "project.read",
            "project.create",
            "project.review",
            "task.manage",
            "repository.read",
            "finding.read",
            "repository.scan",
        }
    ),
    "junior_developer": frozenset({"project.read", "project.create", "task.self"}),
    "security_analyst": frozenset(
        {
            "repository.read",
            "finding.read",
            "security.ingest",
            "security.read",
            "response.propose",
            "response.approve",
            "repository.scan",
            "audit.read",
        }
    ),
}


@dataclass(frozen=True)
class Identity:
    user_id: str
    email: str
    aal: str = "aal1"
    session_id: str | None = None
    expires_at: datetime | None = None
    issued_at: datetime | None = None
    owner_name: str | None = None


@dataclass(frozen=True)
class Principal:
    user_id: str
    organization_id: str
    role: str
    session_id: str | None = None
    aal: str = "aal1"
    expires_at: datetime | None = None
    issued_at: datetime | None = None

    def require(self, permission: str) -> None:
        if permission not in PERMISSIONS.get(self.role, frozenset()):
            raise HTTPException(403, "Permission denied")


_jwks: jwt.PyJWKClient | None = None


def identity(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> Identity:
    global _jwks
    config = settings()
    if not credentials:
        raise HTTPException(401, "Authentication required", headers={"WWW-Authenticate": "Bearer"})
    if not config.supabase_url:
        raise HTTPException(503, "Identity provider is not configured")
    issuer = config.supabase_url.rstrip("/") + "/auth/v1"
    if _jwks is None:
        _jwks = jwt.PyJWKClient(issuer + "/.well-known/jwks.json", timeout=5, lifespan=300)
    try:
        key = _jwks.get_signing_key_from_jwt(credentials.credentials)
        claims = jwt.decode(
            credentials.credentials,
            key.key,
            algorithms=["ES256", "RS256"],
            audience=config.jwt_audience,
            issuer=issuer,
            options={"require": ["exp", "iat", "sub", "aud", "iss", "session_id"]},
        )
        uid = str(UUID(claims["sub"]))
        email = claims.get("email", "").strip().lower()
        if not email or claims.get("is_anonymous", False):
            raise ValueError("Verified email identity required")
        from app.identity_provider import SupabaseAuth, owner_name_from_profile

        profile = SupabaseAuth().request("user", {}, token=credentials.credentials, method="GET")
        if profile.get("id") != uid or not profile.get("email_confirmed_at"):
            raise ValueError("Verified email identity required")
        email = str(profile.get("email", "")).strip().lower()
        if not email:
            raise ValueError("Verified provider email required")
        return Identity(
            uid,
            email,
            str(claims.get("aal", "aal1")),
            str(UUID(claims["session_id"])),
            datetime.fromtimestamp(float(claims["exp"]), UTC),
            datetime.fromtimestamp(float(claims["iat"]), UTC),
            owner_name_from_profile(profile),
        )
    except PyJWKClientConnectionError:
        raise HTTPException(503, "Identity signing keys are temporarily unavailable") from None
    except (
        jwt.PyJWTError,
        ValueError,
        KeyError,
        TypeError,
        AttributeError,
        OverflowError,
    ) as from_error:
        raise HTTPException(
            401, "Invalid or expired identity", headers={"WWW-Authenticate": "Bearer"}
        ) from from_error


def authenticated_identity(
    who: Annotated[Identity, Depends(identity)],
    db: Annotated[Session, Depends(session, scope="function")],
    request: Request,
) -> Identity:
    from app.sessions import track_identity

    track_identity(db, who, request)
    return who


def principal(
    who: Annotated[Identity, Depends(authenticated_identity)],
    db: Annotated[Session, Depends(session, scope="function")],
    organization: Annotated[UUID, Header(alias="X-Organization-ID")],
) -> Principal:
    org = str(organization)
    tenant_context(db, org, who.user_id)
    membership = db.scalar(
        select(Membership)
        .join(Organization, Organization.id == Membership.organization_id)
        .where(
            Membership.organization_id == org,
            Membership.user_id == who.user_id,
            Membership.active.is_(True),
            Organization.status == "active",
        )
    )
    if membership is None:
        raise HTTPException(403, "Active organization membership required")
    if membership.access_not_before is not None and (
        who.issued_at is None or as_utc(who.issued_at) <= as_utc(membership.access_not_before)
    ):
        raise HTTPException(401, "Sign in again after the approved access change")
    if (
        settings().require_privileged_mfa
        and membership.role in {"owner", "hr", "security_analyst"}
        and who.aal != "aal2"
    ):
        raise HTTPException(403, "MFA assurance level 2 is required for privileged access")
    return Principal(
        who.user_id, org, membership.role, who.session_id, who.aal, who.expires_at, who.issued_at
    )


def permission(name: str):
    def dependency(p: Annotated[Principal, Depends(principal)]) -> Principal:
        p.require(name)
        return p

    return dependency
