import hashlib
import json
from collections import defaultdict
from decimal import ROUND_HALF_UP, Decimal

from fastapi import HTTPException
from sqlalchemy import func, select, union
from sqlalchemy.orm import Session

from app.auth import Principal
from app.enterprise_schemas import BudgetInput, CostInput, FinanceSummary
from app.models import Budget, CostRecord, Membership, identifier
from app.services import emit, lock_tenant

FINANCE_GROUP_LIMIT = 10000


def write_authority(db: Session, p: Principal) -> None:
    p.require("finance.write")
    organization = lock_tenant(db, p.organization_id)
    if organization is not None:
        db.refresh(organization, attribute_names=["status"])
    if organization is None or organization.status != "active":
        raise HTTPException(409, "Active organization required")
    member = db.get(
        Membership, (p.organization_id, p.user_id), with_for_update=True, populate_existing=True
    )
    if member is None or not member.active:
        raise HTTPException(403, "Active finance authority required")
    Principal(member.user_id, p.organization_id, member.role).require("finance.write")


def record_cost(db: Session, p: Principal, data: CostInput) -> CostRecord:
    write_authority(db, p)
    values = data.model_dump(exclude={"request_key"})
    amount = data.amount.quantize(Decimal("0.01"))
    values["amount"] = amount if amount else Decimal("0.00")
    if data.usage_quantity is not None:
        quantity = data.usage_quantity.quantize(Decimal("0.000001"))
        values["usage_quantity"] = quantity if quantity else Decimal("0.000000")
    canonical = {**values, "amount": format(values["amount"], ".2f")}
    if values["usage_quantity"] is not None:
        canonical["usage_quantity"] = format(values["usage_quantity"], ".6f")
    digest = hashlib.sha256(
        json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    previous = db.scalar(
        select(CostRecord).where(
            CostRecord.organization_id == p.organization_id,
            CostRecord.request_key == str(data.request_key),
        )
    )
    if previous is not None:
        if previous.recorded_by != p.user_id or previous.request_digest != digest:
            raise HTTPException(409, "Request key is bound to another actor or cost")
        return previous
    record = CostRecord(
        id=identifier(),
        organization_id=p.organization_id,
        request_key=str(data.request_key),
        request_digest=digest,
        recorded_by=p.user_id,
        **values,
    )
    db.add(record)
    db.flush()
    emit(db, p, "finance.cost.recorded", record.id)
    return record


def record_budget(db: Session, p: Principal, data: BudgetInput) -> Budget:
    write_authority(db, p)
    amount = data.amount.quantize(Decimal("0.01")) if data.amount else Decimal("0.00")
    previous = db.scalar(
        select(Budget).where(
            Budget.organization_id == p.organization_id,
            Budget.period == data.period,
            Budget.currency == data.currency,
        )
    )
    if previous is not None:
        if previous.amount != amount:
            raise HTTPException(
                409, "A different budget already exists for this period and currency"
            )
        return previous
    record = Budget(
        id=identifier(),
        organization_id=p.organization_id,
        period=data.period,
        currency=data.currency,
        amount=amount,
    )
    db.add(record)
    db.flush()
    emit(db, p, "finance.budget.recorded", record.id)
    return record


def budget_variances(
    db: Session, p: Principal, currency: str, limit: int, offset: int
) -> list[dict]:
    p.require("finance.read")
    spent = (
        select(CostRecord.period, func.sum(CostRecord.amount).label("actual"))
        .where(CostRecord.organization_id == p.organization_id, CostRecord.currency == currency)
        .group_by(CostRecord.period)
        .subquery()
    )
    planned = (
        select(Budget.period, Budget.amount)
        .where(Budget.organization_id == p.organization_id, Budget.currency == currency)
        .subquery()
    )
    periods = union(select(spent.c.period), select(planned.c.period)).subquery()
    query = (
        select(periods.c.period, planned.c.amount, func.coalesce(spent.c.actual, 0))
        .select_from(
            periods.outerjoin(planned, planned.c.period == periods.c.period).outerjoin(
                spent, spent.c.period == periods.c.period
            )
        )
        .order_by(periods.c.period)
        .limit(limit)
        .offset(offset)
    )
    output = []
    for period, budget, actual in db.execute(query):
        actual = Decimal(actual).quantize(Decimal("0.01"))
        variance = actual - budget if budget is not None else None
        percent = (
            (variance / budget * 100).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            if budget
            else None
        )
        output.append(
            {
                "period": period,
                "currency": currency,
                "budget": budget,
                "actual": actual,
                "variance": variance,
                "variance_percent": percent,
                "over_budget": variance > 0 if variance is not None else None,
            }
        )
    return output


def summarize(db: Session, p: Principal, currency: str) -> FinanceSummary:
    records = db.execute(
        select(CostRecord.period, CostRecord.department, func.sum(CostRecord.amount))
        .where(CostRecord.organization_id == p.organization_id, CostRecord.currency == currency)
        .group_by(CostRecord.period, CostRecord.department)
        .order_by(CostRecord.period, CostRecord.department)
        .limit(FINANCE_GROUP_LIMIT + 1)
    ).all()
    if len(records) > FINANCE_GROUP_LIMIT:
        raise HTTPException(503, "Financial summary exceeds the supported group bound")
    months: dict[str, Decimal] = defaultdict(Decimal)
    departments: dict[str, Decimal] = defaultdict(Decimal)
    for period, department, amount in records:
        months[period] += amount
        departments[department] += amount
    periods = sorted(months)
    # Forecast only from three consecutive observed months, never fabricate missing months.
    forecast = None
    if len(periods) >= 3:
        serials = [int(month[:4]) * 12 + int(month[5:]) for month in periods[-3:]]
        if serials[1] == serials[0] + 1 and serials[2] == serials[1] + 1:
            forecast = (sum((months[m] for m in periods[-3:]), Decimal(0)) / 3).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
    return FinanceSummary(
        currency=currency,
        total=sum(months.values(), Decimal(0)),
        months=dict(months),
        departments=dict(departments),
        forecast_next_month=forecast,
        forecast_method="three consecutive observed months arithmetic mean; insufficient data returns null",
    )
