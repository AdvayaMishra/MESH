"""Tenant-bound document preservation; a hold never grants content access."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from fastapi import HTTPException
from pydantic import ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import Principal
from app.document_authority import authority
from app.models import DocumentHold, Employee, IdentityDocument, now
from app.schemas import Input
from app.services import audit, scoped


class HoldInput(Input):
    request_key: UUID
    reason_code: Literal["dispute", "investigation", "regulatory", "other"]


class ReleaseInput(Input):
    reason_code: Literal["resolved", "entered_in_error", "other"]


class HoldOutput(Input):
    model_config = ConfigDict(from_attributes=True, extra="forbid")
    id: str
    document_id: str
    reason_code: str
    placed_by: str
    created_at: datetime
    released_at: datetime | None
    released_by: str | None
    release_reason: str | None


def independent_document(db: Session, p: Principal, document_id: str) -> IdentityDocument:
    record = scoped(db, IdentityDocument, p, document_id, lock=True)
    employee = scoped(db, Employee, p, record.employee_id)
    if employee.user_id == p.user_id:
        raise HTTPException(409, "Independent HR document preservation review required")
    return record


def reject_held_processing(db: Session, p: Principal, record: IdentityDocument) -> None:
    if db.scalar(
        select(DocumentHold.id)
        .where(
            DocumentHold.organization_id == p.organization_id,
            DocumentHold.document_id == record.id,
            DocumentHold.released_at.is_(None),
        )
        .limit(1)
    ):
        raise HTTPException(409, "Held document processing is suspended")


def place(db: Session, p: Principal, document_id: str, data: HoldInput) -> DocumentHold:
    authority(db, p)
    record = independent_document(db, p, document_id)
    previous = db.scalar(
        select(DocumentHold).where(
            DocumentHold.organization_id == p.organization_id,
            DocumentHold.request_key == str(data.request_key),
        )
    )
    if previous:
        if (previous.document_id, previous.placed_by, previous.reason_code) != (
            record.id,
            p.user_id,
            data.reason_code,
        ):
            raise HTTPException(409, "Hold request key already bound to another request")
        return previous
    if record.status == "deleted":
        raise HTTPException(410, "Deleted documents cannot be preserved")
    active = db.scalar(
        select(DocumentHold.id)
        .where(
            DocumentHold.organization_id == p.organization_id,
            DocumentHold.document_id == record.id,
            DocumentHold.released_at.is_(None),
        )
        .limit(1)
    )
    if active:
        raise HTTPException(409, "Document already has an active hold")
    hold = DocumentHold(
        organization_id=p.organization_id,
        document_id=record.id,
        request_key=str(data.request_key),
        reason_code=data.reason_code,
        placed_by=p.user_id,
    )
    db.add(hold)
    db.flush()
    if record.ocr_status in {"queued", "running"}:
        record.ocr_status, record.ocr_lease_until = "cancelled", None
    audit(db, p, "employee.document.hold_placed", hold.id)
    return hold


def release(db: Session, p: Principal, hold_id: str, data: ReleaseInput) -> DocumentHold:
    authority(db, p)
    hold = scoped(db, DocumentHold, p, hold_id, lock=True)
    independent_document(db, p, hold.document_id)
    if hold.placed_by == p.user_id:
        raise HTTPException(409, "A different HR reviewer must release this hold")
    if hold.released_at is not None:
        if hold.released_by != p.user_id or hold.release_reason != data.reason_code:
            raise HTTPException(409, "Hold already released by another decision")
        return hold
    hold.released_at, hold.released_by, hold.release_reason = now(), p.user_id, data.reason_code
    audit(db, p, "employee.document.hold_released", hold.id)
    return hold
