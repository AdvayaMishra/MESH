"""Explicit setup status and read-only illustrative data, separate from live collection."""

from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.api import DB, P
from app.aws_billing import CurrencyCost
from app.billing import BillingBatch, BillingObservation, FixtureBillingAdapter
from app.billing_collections import current_authority
from app.cloud_configuration import ConnectionStatus, connection_status
from app.cloud_context import authorize
from app.core.config import settings
from app.models import now
from app.schemas import Month
from app.services import audit

router = APIRouter(prefix="/api/v1/cloud-integrations/aws", tags=["Cloud integration setup"])


class SampleBilling(BaseModel):
    organization_id: UUID
    data_source: Literal["sample"] = "sample"
    synthetic: Literal[True] = True
    provider_verified: Literal[False] = False
    invoice_verified: Literal[False] = False
    affects_recorded_totals: Literal[False] = False
    generated_at: datetime
    batch: BillingBatch
    totals: list[CurrencyCost]
    notice: str = (
        "Illustrative sample amounts; no cloud account, provider request or recorded spending."
    )


@router.get("/posture/status", response_model=ConnectionStatus)
def posture_status(db: DB, p: P):
    """Security-authorized local configuration status; never probes AWS or reveals role credentials."""
    authorize(db, p)
    result = connection_status(p.organization_id, "posture")
    audit(db, p, "security.cloud.connection_status", p.organization_id)
    return result


@router.get("/billing/status", response_model=ConnectionStatus)
def billing_status(db: DB, p: P):
    """Finance-authorized local setup status; configured is explicitly unverified."""
    current_authority(db, p)
    result = connection_status(p.organization_id, "billing")
    audit(db, p, "finance.billing.connection_status", p.organization_id)
    return result


@router.get("/billing/sample", response_model=SampleBilling)
def billing_sample(db: DB, p: P, period: Month | None = None):
    """Explicit development-only sample; never a fallback or a stored/live billing report."""
    current_authority(db, p)
    if settings().environment != "development":
        raise HTTPException(503, "Sample billing is available only in development")
    period = period or now().strftime("%Y-%m")
    rows = [
        BillingObservation(
            source_reference="sample:compute:v1",
            period=period,
            department="Engineering",
            currency="USD",
            amount=Decimal("120.00"),
            usage_quantity=Decimal("720"),
            usage_unit="hours",
        ),
        BillingObservation(
            source_reference="sample:storage:v1",
            period=period,
            department="Engineering",
            currency="USD",
            amount=Decimal("35.50"),
            usage_quantity=Decimal("100"),
            usage_unit="gib_months",
        ),
        BillingObservation(
            source_reference="sample:requests:v1",
            period=period,
            department="Operations",
            currency="EUR",
            amount=Decimal("10.00"),
            usage_quantity=Decimal("1000"),
            usage_unit="requests",
        ),
    ]
    batch = FixtureBillingAdapter("aws", rows).collect(period)
    totals: dict[str, Decimal] = {}
    for row in batch.observations:
        totals[row.currency] = totals.get(row.currency, Decimal(0)) + row.amount
    audit(db, p, "finance.billing.sample_read", p.organization_id)
    return SampleBilling(
        organization_id=UUID(p.organization_id),
        generated_at=now(),
        batch=batch,
        totals=[
            CurrencyCost(currency=currency, amount=amount)
            for currency, amount in sorted(totals.items())
        ],
    )
