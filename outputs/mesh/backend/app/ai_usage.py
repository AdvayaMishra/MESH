"""Bounded, currency-separated recorded AI usage; never vendor invoice reconciliation."""

from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import case, func, or_, select

from app.ai_accounting import usage_period_filter
from app.api import DB, Limit, Offset
from app.enterprise_api import FINANCE
from app.models import AIUsage, now
from app.services import audit

router = APIRouter(prefix="/api/v1")


class UsageGroup(BaseModel):
    provider: str
    model: str | None
    currency: str | None
    recorded_requests: int
    input_units: int
    output_units: int
    known_estimated_cost: Decimal | None
    unpriced_requests: int


class UsageSummary(BaseModel):
    month: str
    period_start: datetime
    period_end_exclusive: datetime
    groups: list[UsageGroup]
    total_groups: int
    limit: int
    offset: int
    period_basis: Literal["durable_admission_month_or_legacy_creation_month"] = (
        "durable_admission_month_or_legacy_creation_month"
    )
    recorded_successful_only: Literal[True] = True
    failed_or_ambiguous_dispatches_included: Literal[False] = False
    provider_invoice_reconciled: Literal[False] = False


def month_bounds(value: str | None) -> tuple[str, datetime, datetime]:
    if value is None:
        value = now().strftime("%Y-%m")
    try:
        start = datetime.strptime(value, "%Y-%m").replace(tzinfo=UTC)
        if not 1900 <= start.year <= 9998 or start.strftime("%Y-%m") != value:
            raise ValueError("Month outside supported range")
        end = (
            start.replace(year=start.year + 1, month=1)
            if start.month == 12
            else start.replace(month=start.month + 1)
        )
    except ValueError:
        raise HTTPException(422, "Month must be YYYY-MM, years 1900 through 9998") from None
    return value, start, end


@router.get("/ai/usage/summary", response_model=UsageSummary)
def usage_summary(
    db: DB,
    p: FINANCE,
    month: Annotated[str | None, Query(pattern=r"^[0-9]{4}-[0-9]{2}$")] = None,
    limit: Limit = 50,
    offset: Offset = 0,
):
    value, start, end = month_bounds(month)
    audit(db, p, "ai.usage.summary.read", p.organization_id)
    aggregate = (
        select(
            AIUsage.provider,
            AIUsage.model,
            AIUsage.billing_currency,
            func.count().label("requests"),
            func.sum(AIUsage.input_units).label("input_units"),
            func.sum(AIUsage.output_units).label("output_units"),
            func.sum(AIUsage.estimated_cost).label("known_cost"),
            func.sum(
                case(
                    (or_(AIUsage.estimated_cost.is_(None), AIUsage.billing_currency.is_(None)), 1),
                    else_=0,
                )
            ).label("unpriced"),
            func.count().over().label("total_groups"),
        )
        .where(
            AIUsage.organization_id == p.organization_id,
            usage_period_filter(start),
        )
        .group_by(AIUsage.provider, AIUsage.model, AIUsage.billing_currency)
    )
    rows = db.execute(
        aggregate.order_by(AIUsage.provider, AIUsage.model, AIUsage.billing_currency)
        .limit(limit)
        .offset(offset)
    ).all()
    total = (
        int(rows[0].total_groups)
        if rows
        else int(db.scalar(select(func.count()).select_from(aggregate.subquery())) or 0)
    )
    return UsageSummary(
        month=value,
        period_start=start,
        period_end_exclusive=end,
        groups=[
            UsageGroup(
                provider=row.provider,
                model=row.model,
                currency=row.billing_currency,
                recorded_requests=row.requests,
                input_units=row.input_units,
                output_units=row.output_units,
                known_estimated_cost=row.known_cost if row.billing_currency else None,
                unpriced_requests=row.unpriced,
            )
            for row in rows
        ],
        total_groups=total,
        limit=limit,
        offset=offset,
    )
