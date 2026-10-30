from typing import Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import select
from starlette.concurrency import run_in_threadpool

from app.api import DB, Limit, Offset, P
from app.core.config import settings
from app.core.time import as_utc
from app.document_holds import (
    HoldInput,
    HoldOutput,
    ReleaseInput,
    authority,
    place,
    reject_held_processing,
    release,
)
from app.document_ocr import Suggestions, cipher, decrypt, pending
from app.documents import PrivateStorage, document_key, expire, store
from app.enterprise_api import HR
from app.enterprise_schemas import (
    Decision,
    DocumentOutput,
    DocumentQueue,
    DocumentQueueItem,
    SignedDocument,
)
from app.models import DocumentHold, Employee, IdentityDocument, now
from app.services import audit, emit, scoped

router = APIRouter(prefix="/api/v1")


@router.get("/hr/identity-documents", response_model=DocumentQueue)
def review_queue(
    db: DB,
    p: HR,
    limit: Limit = 50,
    offset: Offset = 0,
    employee_id: UUID | None = None,
    status: Literal["pending_hr", "approved", "rejected", "deleted", "all"] = "pending_hr",
    include_expired: bool = False,
):
    """List tenant document metadata; pending, unexpired documents are the default review queue."""
    authority(db, p)
    cutoff = now()
    held = (
        select(DocumentHold.id)
        .where(
            DocumentHold.organization_id == IdentityDocument.organization_id,
            DocumentHold.document_id == IdentityDocument.id,
            DocumentHold.released_at.is_(None),
        )
        .exists()
        .label("active_hold")
    )
    query = select(
        IdentityDocument.id,
        IdentityDocument.employee_id,
        IdentityDocument.media_type,
        IdentityDocument.status,
        IdentityDocument.expires_at,
        IdentityDocument.ocr_status,
        IdentityDocument.created_at,
        held,
    ).where(IdentityDocument.organization_id == p.organization_id)
    if employee_id is not None:
        scoped(db, Employee, p, str(employee_id))
        query = query.where(IdentityDocument.employee_id == str(employee_id))
    if status != "all":
        query = query.where(IdentityDocument.status == status)
    if not include_expired:
        query = query.where(IdentityDocument.expires_at > cutoff)
    rows = (
        db.execute(
            query.order_by(IdentityDocument.created_at.desc(), IdentityDocument.id)
            .limit(limit + 1)
            .offset(offset)
        )
        .mappings()
        .all()
    )
    audit(db, p, "employee.document.queue_access", p.organization_id)
    return DocumentQueue(
        items=[
            DocumentQueueItem.model_validate(
                {**row, "expired": as_utc(row["expires_at"]) <= cutoff}
            )
            for row in rows[:limit]
        ],
        limit=limit,
        offset=offset,
        has_more=len(rows) > limit,
    )


@router.post(
    "/hr/identity-documents/{document_id}/holds", response_model=HoldOutput, status_code=201
)
def place_hold(document_id: UUID, data: HoldInput, db: DB, p: HR):
    """Preserve a tenant document without extending content access; exact request replays are idempotent."""
    return place(db, p, str(document_id), data)


@router.get("/hr/identity-documents/{document_id}/holds", response_model=list[HoldOutput])
def list_holds(document_id: UUID, db: DB, p: HR, limit: Limit = 50, offset: Offset = 0):
    """Return bounded, audited preservation history without object paths or OCR content."""
    authority(db, p)
    scoped(db, IdentityDocument, p, str(document_id))
    audit(db, p, "employee.document.holds_access", str(document_id))
    return db.scalars(
        select(DocumentHold)
        .where(
            DocumentHold.organization_id == p.organization_id,
            DocumentHold.document_id == str(document_id),
        )
        .order_by(DocumentHold.created_at.desc(), DocumentHold.id)
        .limit(limit)
        .offset(offset)
    ).all()


@router.post("/hr/identity-document-holds/{hold_id}/release", response_model=HoldOutput)
def release_hold(hold_id: UUID, data: ReleaseInput, db: DB, p: HR):
    """Release once through a different HR reviewer; conflicting decisions return 409."""
    return release(db, p, str(hold_id), data)


@router.post(
    "/employees/{employee_id}/identity-documents", response_model=DocumentOutput, status_code=201
)
async def upload(employee_id: UUID, request: Request, db: DB, p: P):
    employee = scoped(db, Employee, p, str(employee_id))
    if employee.user_id != p.user_id:
        raise HTTPException(403, "Only the employee may upload their identity document")
    content = await request.body()
    return await run_in_threadpool(
        store, db, p, employee.id, request.headers.get("content-type", ""), content
    )


@router.get("/hr/identity-documents/{document_id}/signed-url", response_model=SignedDocument)
def signed_url(document_id: UUID, db: DB, p: HR):
    authority(db, p)
    record = scoped(db, IdentityDocument, p, str(document_id))
    if record.status == "deleted" or as_utc(record.expires_at) <= now():
        raise HTTPException(410, "Identity document expired")
    audit(db, p, "employee.document.access", record.id)
    return SignedDocument(url=PrivateStorage().sign(document_key(record, p.organization_id)))


@router.post("/hr/identity-documents/{document_id}/decision", response_model=DocumentOutput)
def review(document_id: UUID, data: Decision, db: DB, p: HR):
    authority(db, p)
    record = scoped(db, IdentityDocument, p, str(document_id), lock=True)
    employee = scoped(db, Employee, p, record.employee_id, lock=True)
    if (
        employee.user_id == p.user_id
        or record.status != "pending_hr"
        or as_utc(record.expires_at) <= now()
    ):
        raise HTTPException(409, "Independent HR review of an unexpired pending document required")
    if record.ocr_status in {"queued", "running"}:
        raise HTTPException(409, "Wait for OCR or explicitly select manual review")
    record.status, record.reviewed_by = data.decision, p.user_id
    employee.verification_status = data.decision
    emit(
        db,
        p,
        "employee.verified" if data.decision == "approved" else "employee.verification.rejected",
        employee.id,
    )
    return record


@router.get("/hr/identity-documents/{document_id}/ocr", response_model=Suggestions | None)
def ocr_result(document_id: UUID, db: DB, p: HR):
    authority(db, p)
    record = scoped(db, IdentityDocument, p, str(document_id))
    if record.status == "deleted" or as_utc(record.expires_at) <= now():
        raise HTTPException(410, "Identity document expired")
    audit(db, p, "employee.document.ocr_access", record.id)
    return decrypt(record)


@router.post("/hr/identity-documents/{document_id}/ocr/retry", response_model=DocumentOutput)
def retry_ocr(document_id: UUID, db: DB, p: HR):
    authority(db, p)
    if not settings().document_ocr_enabled:
        raise HTTPException(503, "Private OCR is not enabled")
    cipher()
    record = scoped(db, IdentityDocument, p, str(document_id), lock=True)
    reject_held_processing(db, p, record)
    pending(record)
    if record.ocr_status not in {"failed", "cancelled", "not_configured", "manual_review"}:
        raise HTTPException(409, "OCR is already pending or completed")
    record.ocr_status, record.ocr_attempts = "queued", 0
    record.ocr_lease_until, record.ocr_ciphertext, record.ocr_error_code = None, None, None
    record.ocr_completed_at = None
    audit(db, p, "employee.document.ocr_retry", record.id)
    return record


@router.post(
    "/hr/identity-documents/{document_id}/ocr/manual-review", response_model=DocumentOutput
)
def manual_ocr(document_id: UUID, db: DB, p: HR):
    authority(db, p)
    record = scoped(db, IdentityDocument, p, str(document_id), lock=True)
    reject_held_processing(db, p, record)
    pending(record)
    employee = scoped(db, Employee, p, record.employee_id, lock=True)
    if employee.user_id == p.user_id:
        raise HTTPException(409, "Independent HR review required")
    record.ocr_status, record.ocr_ciphertext, record.ocr_lease_until = "manual_review", None, None
    record.ocr_error_code, record.ocr_completed_at = None, None
    audit(db, p, "employee.document.ocr_manual_review", record.id)
    return record


@router.post("/hr/identity-documents/expire")
def expire_documents(db: DB, p: HR) -> dict[str, int]:
    authority(db, p)
    return {"expired": expire(db, p)}
