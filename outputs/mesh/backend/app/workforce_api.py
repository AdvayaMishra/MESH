from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Path
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select

from app.api import DB, Limit, Offset, P
from app.enterprise_api import HR
from app.enterprise_schemas import Decision, LeaveOutput
from app.leave_policy import reserved_days
from app.lifecycle_integrations import SCIMClient
from app.models import (
    Employee,
    EmploymentChange,
    EmploymentTerms,
    IntegrationAccount,
    JobRole,
    LeaveEntitlement,
    LeaveRequest,
    LifecyclePlan,
    Membership,
    identifier,
    now,
)
from app.schemas import Input, Money
from app.services import audit, emit, scoped

router = APIRouter(prefix="/api/v1/hr")


class JobRoleInput(Input):
    title: Annotated[str, Field(min_length=1, max_length=100)]
    grade: Annotated[str, Field(min_length=1, max_length=40)]
    version: Annotated[int, Field(ge=1)]
    currency: Annotated[str, Field(pattern=r"^[A-Z]{3}$")]
    minimum_base: Money
    maximum_base: Money

    @model_validator(mode="after")
    def range(self):
        if self.maximum_base < self.minimum_base:
            raise ValueError("Invalid salary range")
        return self


class JobRoleOutput(JobRoleInput):
    id: str
    model_config = {"from_attributes": True}


class EmploymentInput(Input):
    employee_id: UUID
    job_role_id: UUID
    base: Money
    effective_on: date
    reason: Annotated[str, Field(min_length=1, max_length=1000)]

    @model_validator(mode="after")
    def monthly_boundary(self):
        if self.effective_on.day != 1:
            raise ValueError("Monthly salary changes take effect on the first day of a month")
        return self


class EmploymentOutput(BaseModel):
    model_config = {"from_attributes": True}
    id: str
    employee_id: str
    job_role_id: str
    previous_terms_id: str | None
    base: Decimal
    effective_on: date
    reason: str
    proposed_by: str
    reviewed_by: str | None
    status: str
    resolution_reason: str | None
    resolved_at: datetime | None


class WithdrawalInput(Input):
    reason: Annotated[str, Field(min_length=8, max_length=1000)]


class TermsOutput(BaseModel):
    model_config = {"from_attributes": True}
    id: str
    employee_id: str
    job_role_id: str
    change_id: str
    base: Decimal
    currency: str
    effective_on: date


class AllowanceInput(Input):
    allowance_days: Annotated[int, Field(ge=0, le=366)]
    counting: Literal["calendar", "weekdays"] = "weekdays"
    holidays: Annotated[list[date], Field(max_length=366)] = Field(default_factory=list)

    @model_validator(mode="after")
    def unique_holidays(self):
        if len(set(self.holidays)) != len(self.holidays):
            raise ValueError("Holiday dates must be unique")
        return self


class SCIMAccountInput(Input):
    external_id: Annotated[str, Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$")]


class IntegrationOutput(BaseModel):
    model_config = {"from_attributes": True}
    id: str
    user_id: str
    provider: str
    external_id: str


class BalanceOutput(BaseModel):
    employee_id: str
    year: int
    configured: bool
    allowance_days: int | None
    reserved_days: int
    remaining_days: int | None
    counting: str | None
    holidays: list[date] = Field(default_factory=list)


def latest_terms(db, org, employee):
    return db.scalar(
        select(EmploymentTerms)
        .where(
            EmploymentTerms.organization_id == org,
            EmploymentTerms.employee_id == employee,
        )
        .order_by(EmploymentTerms.effective_on.desc(), EmploymentTerms.id.desc())
        .limit(1)
    )


@router.post(
    "/employees/{employee_id}/scim-account", response_model=IntegrationOutput, status_code=201
)
def scim_link(employee_id: UUID, data: SCIMAccountInput, db: DB, p: HR):
    employee = scoped(db, Employee, p, str(employee_id), lock=True)
    member = db.get(Membership, (p.organization_id, employee.user_id))
    if (
        member is None
        or not member.active
        or member.role in {"owner", "hr"}
        or employee.status == "offboarded"
    ):
        raise HTTPException(409, "Active nonprivileged employee membership required")
    current = db.scalar(
        select(IntegrationAccount).where(
            IntegrationAccount.organization_id == p.organization_id,
            IntegrationAccount.provider == "scim",
            (
                (IntegrationAccount.user_id == member.user_id)
                | (IntegrationAccount.external_id == data.external_id)
            ),
        )
    )
    if current:
        if current.user_id != member.user_id or current.external_id != data.external_id:
            raise HTTPException(
                409, "SCIM account is already linked; reviewed reconciliation is required"
            )
        return current
    if db.scalar(
        select(LifecyclePlan.id)
        .where(
            LifecyclePlan.organization_id == p.organization_id,
            LifecyclePlan.employee_id == employee.id,
            LifecyclePlan.status.in_(["proposed", "approved", "reconciliation_required"]),
        )
        .limit(1)
    ):
        raise HTTPException(
            409, "Resolve the existing access plan before changing integration links"
        )
    SCIMClient(p.organization_id).user(data.external_id, member.email)
    record = IntegrationAccount(
        id=identifier(),
        organization_id=p.organization_id,
        user_id=member.user_id,
        provider="scim",
        external_id=data.external_id,
    )
    db.add(record)
    emit(db, p, "employee.scim_account.linked", record.id)
    return record


@router.post("/job-roles", response_model=JobRoleOutput, status_code=201)
def job_role_create(data: JobRoleInput, db: DB, p: HR):
    record = JobRole(id=identifier(), organization_id=p.organization_id, **data.model_dump())
    db.add(record)
    emit(db, p, "employee.job_role.created", record.id)
    return record


@router.get("/job-roles", response_model=list[JobRoleOutput])
def job_roles(db: DB, p: HR, limit: Limit = 50, offset: Offset = 0):
    return db.scalars(
        select(JobRole)
        .where(JobRole.organization_id == p.organization_id)
        .order_by(JobRole.title, JobRole.grade, JobRole.version)
        .limit(limit)
        .offset(offset)
    ).all()


@router.post("/employment-changes", response_model=EmploymentOutput, status_code=201)
def employment_propose(data: EmploymentInput, db: DB, p: HR):
    employee = scoped(db, Employee, p, str(data.employee_id), lock=True)
    member = db.get(Membership, (p.organization_id, employee.user_id))
    if employee.status == "offboarded" or member is None or not member.active:
        raise HTTPException(409, "Active employee membership required")
    role = scoped(db, JobRole, p, str(data.job_role_id))
    if not role.minimum_base <= data.base <= role.maximum_base:
        raise HTTPException(422, "Salary is outside the selected job-grade range")
    if data.effective_on < now().date():
        raise HTTPException(
            422, "Backdated salary proposals require a separate adjustment workflow"
        )
    if db.scalar(
        select(EmploymentChange.id)
        .where(
            EmploymentChange.organization_id == p.organization_id,
            EmploymentChange.employee_id == employee.id,
            EmploymentChange.status.in_(["proposed", "approved"]),
        )
        .limit(1)
    ):
        raise HTTPException(409, "An unfinished employment change already exists")
    previous = latest_terms(db, p.organization_id, employee.id)
    if previous and previous.effective_on >= data.effective_on:
        raise HTTPException(409, "A later salary snapshot already exists")
    record = EmploymentChange(
        id=identifier(),
        organization_id=p.organization_id,
        employee_id=employee.id,
        job_role_id=role.id,
        previous_terms_id=previous.id if previous else None,
        base=data.base,
        effective_on=data.effective_on,
        reason=data.reason,
        proposed_by=p.user_id,
    )
    db.add(record)
    emit(db, p, "employee.employment_change.proposed", record.id)
    return record


@router.get("/employment-changes", response_model=list[EmploymentOutput])
def employment_changes(db: DB, p: HR, limit: Limit = 50, offset: Offset = 0):
    audit(db, p, "employee.employment_changes.read", p.organization_id)
    return db.scalars(
        select(EmploymentChange)
        .where(EmploymentChange.organization_id == p.organization_id)
        .order_by(EmploymentChange.created_at, EmploymentChange.id)
        .limit(limit)
        .offset(offset)
    ).all()


@router.post("/employment-changes/{change_id}/decision", response_model=EmploymentOutput)
def employment_decide(change_id: UUID, data: Decision, db: DB, p: HR):
    record = scoped(db, EmploymentChange, p, str(change_id), lock=True)
    employee = scoped(db, Employee, p, record.employee_id)
    if record.proposed_by == p.user_id or employee.user_id == p.user_id:
        raise HTTPException(403, "Independent HR approval is required")
    if record.status != "proposed":
        raise HTTPException(409, "Employment change already reviewed")
    record.status, record.reviewed_by = data.decision, p.user_id
    emit(db, p, "employee.employment_change." + data.decision, record.id)
    return record


@router.post("/employment-changes/{change_id}/apply", response_model=TermsOutput)
def employment_apply(change_id: UUID, db: DB, p: HR):
    record = scoped(db, EmploymentChange, p, str(change_id), lock=True)
    if record.status == "applied":
        return db.scalar(
            select(EmploymentTerms).where(
                EmploymentTerms.organization_id == p.organization_id,
                EmploymentTerms.change_id == record.id,
            )
        )
    if record.status != "approved" or record.effective_on > now().date():
        raise HTTPException(409, "Approved employment change must be due before application")
    employee = scoped(db, Employee, p, record.employee_id, lock=True)
    member = db.get(Membership, (p.organization_id, employee.user_id))
    reviewer = db.get(Membership, (p.organization_id, record.reviewed_by))
    if employee.status == "offboarded" or member is None or not member.active:
        raise HTTPException(409, "Active employee membership required")
    if reviewer is None or not reviewer.active or reviewer.role != "hr":
        raise HTTPException(409, "Reviewer's HR authorization is no longer active")
    current = latest_terms(db, p.organization_id, employee.id)
    if (current.id if current else None) != record.previous_terms_id:
        raise HTTPException(409, "Salary snapshot changed; a new reviewed proposal is required")
    role = scoped(db, JobRole, p, record.job_role_id)
    terms = EmploymentTerms(
        id=identifier(),
        organization_id=p.organization_id,
        employee_id=employee.id,
        job_role_id=role.id,
        change_id=record.id,
        base=record.base,
        currency=role.currency,
        effective_on=record.effective_on,
    )
    db.add(terms)
    record.status = "applied"
    emit(db, p, "employee.employment_change.applied", record.id)
    return terms


@router.post("/employment-changes/{change_id}/withdraw", response_model=EmploymentOutput)
def employment_withdraw(change_id: UUID, data: WithdrawalInput, db: DB, p: HR):
    record = scoped(db, EmploymentChange, p, str(change_id), lock=True)
    if record.status == "rejected" and record.resolution_reason is not None:
        return record
    if record.status not in {"proposed", "approved"}:
        raise HTTPException(409, "Applied or already rejected salary history cannot be withdrawn")
    record.status, record.resolution_reason, record.resolved_at = "rejected", data.reason, now()
    emit(db, p, "employee.employment_change.withdrawn", record.id)
    return record


@router.get("/employees/{employee_id}/employment-terms", response_model=list[TermsOutput])
def employment_history(employee_id: UUID, db: DB, p: HR, limit: Limit = 50, offset: Offset = 0):
    employee = scoped(db, Employee, p, str(employee_id))
    audit(db, p, "employee.employment_terms.read", employee.id)
    return db.scalars(
        select(EmploymentTerms)
        .where(
            EmploymentTerms.organization_id == p.organization_id,
            EmploymentTerms.employee_id == employee.id,
        )
        .order_by(EmploymentTerms.effective_on, EmploymentTerms.id)
        .limit(limit)
        .offset(offset)
    ).all()


@router.put("/employees/{employee_id}/leave-allowance/{year}", response_model=BalanceOutput)
def allowance_set(
    employee_id: UUID,
    year: Annotated[int, Path(ge=2000, le=2200)],
    data: AllowanceInput,
    db: DB,
    p: HR,
):
    employee = scoped(db, Employee, p, str(employee_id), lock=True)
    if employee.user_id == p.user_id:
        raise HTTPException(403, "Independent HR allowance administrator required")
    if any(day.year != year for day in data.holidays):
        raise HTTPException(422, "Holiday dates must belong to the allowance year")
    holidays = sorted(day.isoformat() for day in data.holidays)
    record = db.scalar(
        select(LeaveEntitlement).where(
            LeaveEntitlement.organization_id == p.organization_id,
            LeaveEntitlement.employee_id == employee.id,
            LeaveEntitlement.year == year,
        )
    )
    calendar_changed = record is not None and (
        record.counting != data.counting or sorted(record.holidays) != holidays
    )
    if calendar_changed and db.scalar(
        select(LeaveRequest.id)
        .where(
            LeaveRequest.organization_id == p.organization_id,
            LeaveRequest.employee_id == employee.id,
            LeaveRequest.status.in_(["pending", "approved"]),
            LeaveRequest.starts_on <= date(year, 12, 31),
            LeaveRequest.ends_on >= date(year, 1, 1),
        )
        .limit(1)
    ):
        raise HTTPException(409, "Cannot change leave calendar while leave is reserved")
    reserved = reserved_days(
        db, p.organization_id, employee.id, year, data.counting, holidays=holidays
    )
    if data.allowance_days < reserved:
        raise HTTPException(409, "Allowance cannot be below pending and approved reservations")
    if record is None:
        record = LeaveEntitlement(
            id=identifier(),
            organization_id=p.organization_id,
            employee_id=employee.id,
            year=year,
            allowance_days=data.allowance_days,
            counting=data.counting,
            holidays=holidays,
        )
        db.add(record)
    else:
        record.allowance_days, record.counting = data.allowance_days, data.counting
        record.holidays = holidays
    emit(db, p, "leave.allowance.updated", record.id)
    return BalanceOutput(
        employee_id=employee.id,
        year=year,
        configured=True,
        allowance_days=record.allowance_days,
        reserved_days=reserved,
        remaining_days=record.allowance_days - reserved,
        counting=record.counting,
        holidays=record.holidays,
    )


@router.get("/employees/{employee_id}/leave-allowance/{year}", response_model=BalanceOutput)
def allowance_get(employee_id: UUID, year: Annotated[int, Path(ge=2000, le=2200)], db: DB, p: P):
    employee = scoped(db, Employee, p, str(employee_id))
    if employee.user_id != p.user_id:
        p.require("employee.read")
    record = db.scalar(
        select(LeaveEntitlement).where(
            LeaveEntitlement.organization_id == p.organization_id,
            LeaveEntitlement.employee_id == employee.id,
            LeaveEntitlement.year == year,
        )
    )
    reserved = reserved_days(
        db,
        p.organization_id,
        employee.id,
        year,
        record.counting if record else "calendar",
        holidays=record.holidays if record else None,
    )
    return BalanceOutput(
        employee_id=employee.id,
        year=year,
        configured=record is not None,
        allowance_days=record.allowance_days if record else None,
        reserved_days=reserved,
        remaining_days=record.allowance_days - reserved if record else None,
        counting=record.counting if record else None,
        holidays=record.holidays if record else [],
    )


@router.post("/leave/{leave_id}/cancel", response_model=LeaveOutput)
def leave_cancel(leave_id: UUID, db: DB, p: P):
    record = scoped(db, LeaveRequest, p, str(leave_id), lock=True)
    employee = scoped(db, Employee, p, record.employee_id, lock=True)
    if p.role != "hr" and employee.user_id != p.user_id:
        raise HTTPException(403, "Leave cancellation is restricted to the employee or HR")
    if record.status != "pending" and not (p.role == "hr" and record.status == "approved"):
        raise HTTPException(409, "Leave cannot be cancelled in its current state")
    record.status = "cancelled"
    emit(db, p, "leave.cancelled", record.id)
    return record
