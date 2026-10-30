from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import select

from app.api import DB, Limit, Offset, Who
from app.models import IdentitySession, now
from app.sessions import revoke_all

router = APIRouter(prefix="/api/v1/users/me")


class SessionOutput(BaseModel):
    id: str
    client_hint: str
    created_at: datetime
    last_seen: datetime
    expires_at: datetime
    revoked_at: datetime | None
    revocation_reason: str | None
    current: bool


class SessionRevocations(BaseModel):
    revoked: int
    scope: str = (
        "MESH account sessions; provider refresh sessions are not revoked by this operation"
    )


@router.get("/sessions", response_model=list[SessionOutput])
def sessions(db: DB, who: Who, limit: Limit = 50, offset: Offset = 0):
    records = db.scalars(
        select(IdentitySession)
        .where(IdentitySession.user_id == who.user_id)
        .order_by(IdentitySession.created_at.desc(), IdentitySession.id)
        .limit(limit)
        .offset(offset)
    ).all()
    return [
        SessionOutput(
            id=record.id,
            client_hint=record.client_hint,
            created_at=record.created_at,
            last_seen=record.last_seen,
            expires_at=record.expires_at,
            revoked_at=record.revoked_at,
            revocation_reason=record.revocation_reason,
            current=record.provider_session_id == who.session_id,
        )
        for record in records
    ]


@router.delete("/sessions/{session_id}", response_model=SessionRevocations)
def revoke_session(session_id: UUID, db: DB, who: Who):
    record = db.scalar(
        select(IdentitySession).where(
            IdentitySession.user_id == who.user_id,
            IdentitySession.id == str(session_id),
        )
    )
    if record is None:
        raise HTTPException(404, "Session not found")
    changed = record.revoked_at is None
    if changed:
        record.revoked_at = now()
        record.revocation_reason = "self_revoked"
    return SessionRevocations(revoked=int(changed))


@router.post("/sessions/revoke-others", response_model=SessionRevocations)
def revoke_others(db: DB, who: Who):
    if who.session_id is None:
        raise HTTPException(409, "Current provider session is unknown")
    return SessionRevocations(revoked=revoke_all(db, who.user_id, keep=who.session_id))
