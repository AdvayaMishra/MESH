from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException
from pydantic import Field, field_validator, model_validator
from sqlalchemy import select

from app.api import DB, Limit, Offset
from app.enterprise_api import HR
from app.models import (
    Employee,
    EmploymentTerms,
    Payroll,
    PayrollCalculation,
    PayrollRule,
    identifier,
)
from app.schemas import Input, Money, PayrollOutput
from app.services import emit, scoped

router = APIRouter(prefix="/api/v1/hr")


class Component(Input):
    name: Annotated[str, Field(pattern=r"^[A-Za-z0-9 _-]{1,100}$")]
    kind: Literal["earning", "deduction"]
    formula: Literal["fixed", "percent_of_base"]
    value: Money

    @model_validator(mode="after")
    def percentage(self):
        if self.formula == "percent_of_base" and self.value > 100:
            raise ValueError("Percent must not exceed 100")
        return self


class RuleInput(Input):
    name: Annotated[str, Field(min_length=1, max_length=100)]
    version: Annotated[int, Field(ge=1)]
    currency: Annotated[str, Field(pattern=r"^[A-Z]{3}$")]
    components: Annotated[list[Component], Field(max_length=50)]

    @model_validator(mode="after")
    def unique_names(self):
        if len({component.name for component in self.components}) != len(self.components):
            raise ValueError("Component names must be unique")
        return self


class RuleOutput(RuleInput):
    id: str
    model_config = {"from_attributes": True}


class ComputeInput(Input):
    employee_id: UUID
    rule_id: UUID
    base: Money
    period: Annotated[str, Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")]

    @field_validator("period")
    @classmethod
    def real_month(cls, value: str) -> str:
        date.fromisoformat(value + "-01")
        return value


class Computed(Input):
    payroll: PayrollOutput
    breakdown: list[dict]
    rule_version: int


def calculate(base: Decimal, components: list[Component]) -> tuple[Decimal, Decimal, list[dict]]:
    if not base.is_finite() or base < 0 or base != base.quantize(Decimal("0.01")):
        raise HTTPException(422, "Invalid base pay")
    gross, deductions = base, Decimal(0)
    breakdown = []
    for component in components:
        amount = (
            component.value if component.formula == "fixed" else base * component.value / 100
        ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        if component.kind == "earning":
            gross += amount
        else:
            deductions += amount
        breakdown.append(
            {
                "name": component.name,
                "kind": component.kind,
                "formula": component.formula,
                "value": str(component.value),
                "amount": str(amount),
            }
        )
    if deductions > gross or gross >= Decimal("1000000000000"):
        raise HTTPException(422, "Payroll totals exceed supported bounds")
    return gross, deductions, breakdown


@router.post("/payroll-rules", response_model=RuleOutput, status_code=201)
def rule_create(data: RuleInput, db: DB, p: HR):
    record = PayrollRule(
        id=identifier(),
        organization_id=p.organization_id,
        name=data.name,
        version=data.version,
        currency=data.currency,
        components=[component.model_dump(mode="json") for component in data.components],
    )
    db.add(record)
    emit(db, p, "payroll.rule.created", record.id)
    return record


@router.get("/payroll-rules", response_model=list[RuleOutput])
def rules(db: DB, p: HR, limit: Limit = 50, offset: Offset = 0):
    return db.scalars(
        select(PayrollRule)
        .where(PayrollRule.organization_id == p.organization_id)
        .order_by(PayrollRule.name, PayrollRule.version)
        .limit(limit)
        .offset(offset)
    ).all()


@router.post("/payroll/compute", response_model=Computed, status_code=201)
def compute(data: ComputeInput, db: DB, p: HR):
    employee = scoped(db, Employee, p, str(data.employee_id))
    rule = scoped(db, PayrollRule, p, str(data.rule_id))
    if employee.status == "offboarded":
        raise HTTPException(
            409, "Offboarded employee payroll requires a separately reviewed final settlement"
        )
    period_start = date.fromisoformat(data.period + "-01")
    terms = db.scalar(
        select(EmploymentTerms)
        .where(
            EmploymentTerms.organization_id == p.organization_id,
            EmploymentTerms.employee_id == employee.id,
            EmploymentTerms.effective_on <= period_start,
        )
        .order_by(EmploymentTerms.effective_on.desc())
        .limit(1)
    )
    if terms and (data.base != terms.base or rule.currency != terms.currency):
        raise HTTPException(409, "Payroll must match the independently approved salary snapshot")
    gross, deductions, breakdown = calculate(
        data.base, [Component.model_validate(item) for item in rule.components]
    )
    record = Payroll(
        id=identifier(),
        organization_id=p.organization_id,
        employee_id=employee.id,
        period=data.period,
        currency=rule.currency,
        gross=gross,
        deductions=deductions,
        net=gross - deductions,
    )
    db.add(record)
    db.flush()
    db.add(
        PayrollCalculation(
            organization_id=p.organization_id,
            payroll_id=record.id,
            rule_id=rule.id,
            base=data.base,
            breakdown=breakdown,
        )
    )
    emit(db, p, "payroll.calculated", record.id)
    return Computed(
        payroll=PayrollOutput.model_validate(record), breakdown=breakdown, rule_version=rule.version
    )
