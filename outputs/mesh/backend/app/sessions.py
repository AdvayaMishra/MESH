"""Immediate backend denylist and self-owned session observations, not device attestation."""

import hashlib
import hmac
from datetime import timedelta

from fastapi import HTTPException, Request
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.auth import Identity
from app.core.config import settings
from app.core.db import tenant_context
from app.core.time import as_utc
from app.models import IdentitySession, now


def track_identity(db: Session, who: Identity, request: Request) -> None:
    # Dependency overrides used by fixture tests do not represent provider sessions.
    if who.session_id is None:
        if settings().test_mode:
            return
        raise HTTPException(401, "Provider session identifier is required")
    if who.expires_at is None:
        raise HTTPException(401, "Provider session expiration is required")
    tenant_context(db, "", who.user_id)
    if db.get_bind().dialect.name == "postgresql":
        # One lock order for a user's simultaneous session refresh/revocation requests.
        db.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:uid, 6943))"), {"uid": who.user_id}
        )
    record = db.scalar(
        select(IdentitySession).where(
            IdentitySession.user_id == who.user_id,
            IdentitySession.provider_session_id == who.session_id,
        )
    )
    if record and record.revoked_at is not None:
        raise HTTPException(401, "This session was revoked in MESH")
    if record is None:
        secret = settings().auth_rate_secret
        if secret is None or len(secret.get_secret_value()) < 32:
            raise HTTPException(503, "Account protection key is unavailable")
        hint = "".join(
            char for char in request.headers.get("user-agent", "") if char.isprintable()
        )[:200]
        address = request.client.host if request.client else "unknown"
        digest = hmac.new(
            secret.get_secret_value().encode(), address.encode(), hashlib.sha256
        ).hexdigest()
        record = IdentitySession(
            user_id=who.user_id,
            provider_session_id=who.session_id,
            client_hint=hint,
            ip_digest=digest,
            expires_at=who.expires_at,
        )
        db.add(record)
        db.flush()
    elif as_utc(record.last_seen) <= now() - timedelta(minutes=5):
        record.last_seen = now()
        record.expires_at = max(as_utc(record.expires_at), who.expires_at)


def revoke_all(
    db: Session, user_id: str, *, keep: str | None = None, reason: str = "self_revoked"
) -> int:
    query = select(IdentitySession).where(
        IdentitySession.user_id == user_id, IdentitySession.revoked_at.is_(None)
    )
    if keep:
        query = query.where(IdentitySession.provider_session_id != keep)
    records = db.scalars(query).all()
    for record in records:
        record.revoked_at = now()
        record.revocation_reason = reason
    return len(records)
