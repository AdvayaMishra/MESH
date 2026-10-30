"""Owner-only provisional model dispatch accounting; no automatic provider replay."""

from uuid import UUID

from fastapi import APIRouter, HTTPException
from sqlalchemy import func, select

from app import ai_accounting
from app.ai import authority
from app.ai_receipts_schema import (
    ReceiptDetail,
    ReceiptEventOutput,
    ReceiptOutput,
    ReceiptPage,
    ReceiptState,
    ReconciliationInput,
)
from app.api import DB, Limit, Offset
from app.enterprise_api import FINANCE
from app.models import AIRequest, AIRequestEvent
from app.services import audit

router = APIRouter(prefix="/api/v1/ai/requests")


@router.get("", response_model=ReceiptPage)
def requests(
    db: DB, p: FINANCE, status: ReceiptState | None = None, limit: Limit = 50, offset: Offset = 0
):
    p = authority(db, p, "owner")
    scope = [AIRequest.organization_id == p.organization_id]
    if status is not None:
        scope.append(AIRequest.status == status)
    rows = db.scalars(
        select(AIRequest)
        .where(*scope)
        .order_by(AIRequest.created_at.desc(), AIRequest.id)
        .limit(limit)
        .offset(offset)
    ).all()
    total = int(db.scalar(select(func.count()).select_from(AIRequest).where(*scope)) or 0)
    audit(db, p, "ai.requests.read", p.organization_id)
    return ReceiptPage(
        requests=[ReceiptOutput.model_validate(row) for row in rows],
        total_requests=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{request_id}", response_model=ReceiptDetail)
def detail(request_id: UUID, db: DB, p: FINANCE, limit: Limit = 50, offset: Offset = 0):
    p = authority(db, p, "owner")
    record = db.scalar(
        select(AIRequest).where(
            AIRequest.organization_id == p.organization_id, AIRequest.id == str(request_id)
        )
    )
    if record is None:
        raise HTTPException(404, "AI request not found")
    scope = [
        AIRequestEvent.organization_id == p.organization_id,
        AIRequestEvent.request_id == record.id,
    ]
    rows = db.scalars(
        select(AIRequestEvent)
        .where(*scope)
        .order_by(AIRequestEvent.position)
        .limit(limit)
        .offset(offset)
    ).all()
    total = int(db.scalar(select(func.count()).select_from(AIRequestEvent).where(*scope)) or 0)
    audit(db, p, "ai.request.read", record.id)
    return ReceiptDetail(
        request=ReceiptOutput.model_validate(record),
        events=[ReceiptEventOutput.model_validate(row) for row in rows],
        total_events=total,
        limit=limit,
        offset=offset,
    )


@router.post("/{request_id}/cancel-expired", response_model=ReceiptOutput)
def cancel_expired(request_id: UUID, db: DB, p: FINANCE):
    p = authority(db, p, "owner")
    record = ai_accounting.store_for(db, p).cancel_expired(str(request_id))
    audit(db, p, "ai.request.cancel_expired", record.id)
    return record


@router.post("/{request_id}/reconcile", response_model=ReceiptOutput)
def reconcile(request_id: UUID, data: ReconciliationInput, db: DB, p: FINANCE):
    p = authority(db, p, "owner")
    record = ai_accounting.store_for(db, p).reconcile(str(request_id), data)
    audit(db, p, "ai.request.reconcile", record.id)
    return record
