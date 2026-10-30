"""Finance-authorized billing admission/status/report API; provider calls run in a worker."""

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.orm import defer

from app.api import DB, Limit, Offset, P
from app.aws_billing import AWSBillingReport
from app.billing_collections import (
    cancel_collection,
    current_authority,
    get_collection,
    read_report,
    request_collection,
)
from app.models import BillingCollection
from app.schemas import Input, Month
from app.services import audit

router = APIRouter(prefix="/api/v1/finance/cloud-billing/aws/collections", tags=["Cloud billing"])


class BillingCollectionInput(Input):
    request_key: UUID
    period: Month


class BillingCollectionOutput(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    period: Month
    provider_account_id: Annotated[str, Field(pattern=r"^[0-9]{12}$")]
    status: Literal["queued", "running", "completed", "failed", "ambiguous", "cancelled"]
    attempts: int
    error_code: str | None
    created_at: datetime
    dispatched_at: datetime | None
    finished_at: datetime | None
    provider_queries_may_incur_charges: Literal[True] = True


class BillingCollectionPage(BaseModel):
    items: list[BillingCollectionOutput]
    total: int
    limit: int
    offset: int
    next_offset: int | None


@router.post(
    "",
    response_model=BillingCollectionOutput,
    status_code=202,
    description="Admit one bounded monthly provider read. Request keys are actor/period-bound and replay without another provider call. AWS queries may incur charges. Up to three pending and twenty daily collections per organization; failed/ambiguous reads require an explicit new request key.",
)
def request(data: BillingCollectionInput, db: DB, p: P):
    return request_collection(db, p, request_key=data.request_key, period=data.period)


@router.get("", response_model=BillingCollectionPage)
def history(db: DB, p: P, period: Month | None = None, limit: Limit = 50, offset: Offset = 0):
    current_authority(db, p)
    predicates = [
        BillingCollection.organization_id == p.organization_id,
        BillingCollection.synthetic.is_(False),
    ]
    if period is not None:
        predicates.append(BillingCollection.period == period)
    total = db.scalar(select(func.count()).select_from(BillingCollection).where(*predicates)) or 0
    rows = db.scalars(
        select(BillingCollection)
        .where(*predicates)
        .options(defer(BillingCollection.report))
        .order_by(BillingCollection.created_at.desc(), BillingCollection.id.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    audit(db, p, "finance.billing.collections.read", p.organization_id)
    return BillingCollectionPage(
        items=[BillingCollectionOutput.model_validate(row) for row in rows],
        total=total,
        limit=limit,
        offset=offset,
        next_offset=offset + len(rows) if offset + len(rows) < total and rows else None,
    )


@router.get("/{collection_id}", response_model=BillingCollectionOutput)
def detail(collection_id: UUID, db: DB, p: P):
    record = get_collection(db, p, collection_id)
    audit(db, p, "finance.billing.collection.read", record.id)
    return record


@router.post("/{collection_id}/cancel", response_model=BillingCollectionOutput)
def cancel(collection_id: UUID, db: DB, p: P):
    return cancel_collection(db, p, collection_id)


@router.get(
    "/{collection_id}/report",
    response_model=AWSBillingReport,
    description="Return one immutable account-filtered observation report. Amounts include signed adjustments and separate currency totals. This is not an invoice and does not post into manual costs.",
)
def report(collection_id: UUID, db: DB, p: P):
    return read_report(db, p, collection_id)
