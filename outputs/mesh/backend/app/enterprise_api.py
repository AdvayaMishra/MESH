from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select

from app.api import DB, Limit, Offset, P, Who
from app.auth import Principal, permission
from app.devtrack import active_developer, project_access
from app.enterprise_schemas import (
    BudgetInput,
    BudgetOutput,
    BudgetVarianceOutput,
    CommentInput,
    CommentOutput,
    ComplaintInput,
    ComplaintOutput,
    CostInput,
    CostOutput,
    Decision,
    DepartmentInput,
    DepartmentOutput,
    FinanceSummary,
    InfrastructureUsageOutput,
    JobMetadata,
    LeaveInput,
    LeaveOutput,
    LifecycleInput,
    LifecycleOutput,
    MemberInput,
    MemberOutput,
    SprintInput,
    SprintOutput,
    TaskUpdate,
)
from app.finance import budget_variances, record_budget, record_cost, summarize
from app.hr import execute_lifecycle, propose_lifecycle, request_leave, require_lifecycle_authority
from app.leave_policy import require_capacity
from app.models import (
    Budget,
    Complaint,
    CostRecord,
    Department,
    Employee,
    LeaveRequest,
    LifecyclePlan,
    Membership,
    Outbox,
    Payroll,
    ProjectComment,
    ProjectMember,
    Sprint,
    Task,
    TaskDetail,
    identifier,
    now,
)
from app.schemas import Month, PayrollOutput, TaskOutput, UserProfileOutput
from app.services import audit, emit, scoped, verify_audit

router = APIRouter(prefix="/api/v1")
HR = Annotated[Principal, Depends(permission("employee.write"))]
OWNER = Annotated[Principal, Depends(permission("organization.manage"))]
FINANCE = Annotated[Principal, Depends(permission("finance.read"))]
FINANCE_WRITE = Annotated[Principal, Depends(permission("finance.write"))]


@router.get("/users/me", response_model=UserProfileOutput)
def user_profile(db: DB, p: P, who: Who) -> dict:
    member = db.get(Membership, (p.organization_id, p.user_id))
    if member is None:
        raise HTTPException(403, "Membership unavailable")
    employee = db.scalar(
        select(Employee).where(
            Employee.organization_id == p.organization_id, Employee.user_id == p.user_id
        )
    )
    return {
        "user_id": p.user_id,
        "organization_id": p.organization_id,
        "role": p.role,
        "email": member.email,
        "employee_id": employee.id if employee else None,
        "name": employee.name if employee else who.owner_name,
        "owner_name": who.owner_name if p.role == "owner" else None,
    }


@router.get("/hr/payroll", response_model=list[PayrollOutput])
def payroll_records(
    db: DB,
    p: Annotated[Principal, Depends(permission("payroll.read"))],
    limit: Limit = 50,
    offset: Offset = 0,
):
    audit(db, p, "payroll.read", p.organization_id)
    return db.scalars(
        select(Payroll)
        .where(Payroll.organization_id == p.organization_id)
        .order_by(Payroll.created_at, Payroll.id)
        .limit(limit)
        .offset(offset)
    ).all()


@router.get("/finance/budgets", response_model=list[BudgetOutput])
def budgets(
    db: DB,
    p: FINANCE,
    currency: Annotated[str | None, Query(pattern=r"^[A-Z]{3}$")] = None,
    period: Month | None = None,
    limit: Limit = 50,
    offset: Offset = 0,
):
    query = select(Budget).where(Budget.organization_id == p.organization_id)
    if currency is not None:
        query = query.where(Budget.currency == currency)
    if period is not None:
        query = query.where(Budget.period == period)
    audit(db, p, "finance.budgets.read", p.organization_id)
    return db.scalars(query.order_by(Budget.period, Budget.id).limit(limit).offset(offset)).all()


@router.get("/finance/budgets/{budget_id}/variance")
def budget_variance(budget_id: UUID, db: DB, p: FINANCE) -> dict:
    budget = scoped(db, Budget, p, str(budget_id))
    actual = summarize(db, p, budget.currency).months.get(budget.period, Decimal(0))
    return {
        "budget_id": budget.id,
        "currency": budget.currency,
        "budget": str(budget.amount),
        "actual": str(actual),
        "remaining": str(budget.amount - actual),
    }


@router.get("/audit/integrity")
def audit_integrity(db: DB, p: Annotated[Principal, Depends(permission("audit.read"))]) -> dict:
    return verify_audit(db, p)


@router.get("/jobs", response_model=list[JobMetadata])
def jobs(
    db: DB,
    p: Annotated[Principal, Depends(permission("audit.read"))],
    limit: Limit = 50,
    offset: Offset = 0,
    status: Literal["pending", "delivered", "dead_letter", "cancelled"] | None = None,
    topic: Annotated[str | None, Query(min_length=1, max_length=100)] = None,
):
    query = select(Outbox).where(Outbox.organization_id == p.organization_id)
    if status is not None:
        query = query.where(Outbox.status == status)
    if topic is not None:
        query = query.where(Outbox.topic == topic)
    return db.scalars(
        query.order_by(Outbox.created_at, Outbox.id).limit(limit).offset(offset)
    ).all()


@router.get("/jobs/{job_id}", response_model=JobMetadata)
def job_get(job_id: UUID, db: DB, p: Annotated[Principal, Depends(permission("audit.read"))]):
    return scoped(db, Outbox, p, str(job_id))


@router.post("/jobs/{job_id}/retry")
def retry_job(job_id: UUID, db: DB, p: OWNER) -> dict[str, str]:
    preview = scoped(db, Outbox, p, str(job_id))
    if preview.status != "dead_letter":
        raise HTTPException(409, "Only dead-letter jobs may be retried")
    row = scoped(db, Outbox, p, str(job_id), lock=True)
    if row.status != "dead_letter":
        raise HTTPException(409, "Only dead-letter jobs may be retried")
    row.status, row.attempts, row.available_at = "pending", 0, now()
    audit(db, p, "job.retry.approved", row.id)
    return {"id": row.id, "status": row.status}


@router.post("/hr/departments", response_model=DepartmentOutput, status_code=201)
def department_create(data: DepartmentInput, db: DB, p: HR):
    record = Department(id=identifier(), organization_id=p.organization_id, name=data.name)
    db.add(record)
    emit(db, p, "department.created", record.id)
    return record


@router.get("/hr/departments", response_model=list[DepartmentOutput])
def departments(db: DB, p: HR, limit: Limit = 50, offset: Offset = 0):
    return db.scalars(
        select(Department)
        .where(Department.organization_id == p.organization_id)
        .order_by(Department.id)
        .limit(limit)
        .offset(offset)
    ).all()


@router.post("/hr/leave", response_model=LeaveOutput, status_code=201)
def leave_create(data: LeaveInput, db: DB, p: P):
    return request_leave(db, p, data)


@router.get("/hr/leave", response_model=list[LeaveOutput])
def leaves(db: DB, p: P, limit: Limit = 50, offset: Offset = 0):
    query = (
        select(LeaveRequest)
        .join(
            Employee,
            (Employee.organization_id == LeaveRequest.organization_id)
            & (Employee.id == LeaveRequest.employee_id),
        )
        .where(LeaveRequest.organization_id == p.organization_id)
    )
    if p.role != "hr":
        query = query.where(Employee.user_id == p.user_id)
    audit(db, p, "leave.read", p.user_id)
    return db.scalars(query.order_by(LeaveRequest.id).limit(limit).offset(offset)).all()


@router.post("/hr/leave/{leave_id}/decision", response_model=LeaveOutput)
def leave_decide(leave_id: UUID, data: Decision, db: DB, p: HR):
    record = scoped(db, LeaveRequest, p, str(leave_id), lock=True)
    employee = scoped(db, Employee, p, record.employee_id, lock=True)
    if employee.user_id == p.user_id:
        raise HTTPException(403, "Self approval forbidden")
    if record.status != "pending":
        raise HTTPException(409, "Leave already reviewed")
    if data.decision == "approved":
        if employee.status == "offboarded":
            raise HTTPException(409, "Cannot approve leave for an offboarded employee")
        require_capacity(
            db, p.organization_id, employee.id, record.starts_on, record.ends_on, record.id
        )
    record.status, record.reviewed_by = data.decision, p.user_id
    emit(db, p, "leave." + data.decision, record.id)
    return record


@router.post("/hr/complaints", response_model=ComplaintOutput, status_code=201)
def complaint_create(data: ComplaintInput, db: DB, p: P):
    record = Complaint(
        id=identifier(), organization_id=p.organization_id, author_id=p.user_id, **data.model_dump()
    )
    db.add(record)
    db.flush()
    audit(db, p, "complaint.created", record.id)
    return record


@router.get("/hr/complaints", response_model=list[ComplaintOutput])
def complaints(db: DB, p: P, limit: Limit = 50, offset: Offset = 0):
    query = select(Complaint).where(Complaint.organization_id == p.organization_id)
    if p.role != "hr":
        query = query.where(Complaint.author_id == p.user_id)
    audit(db, p, "complaint.read", p.user_id)
    return db.scalars(query.order_by(Complaint.id).limit(limit).offset(offset)).all()


@router.post("/hr/lifecycle", response_model=LifecycleOutput, status_code=201)
def lifecycle_propose(data: LifecycleInput, db: DB, p: HR):
    return propose_lifecycle(db, p, data)


@router.get("/hr/lifecycle/{plan_id}", response_model=LifecycleOutput)
def lifecycle_get(plan_id: UUID, db: DB, p: P):
    if p.role not in {"hr", "owner"}:
        raise HTTPException(403, "Lifecycle permission required")
    return scoped(db, LifecyclePlan, p, str(plan_id))


@router.post("/hr/lifecycle/{plan_id}/decision", response_model=LifecycleOutput)
def lifecycle_approve(plan_id: UUID, data: Decision, db: DB, p: OWNER):
    require_lifecycle_authority(db, p, "organization.manage")
    plan = scoped(db, LifecyclePlan, p, str(plan_id), lock=True)
    if plan.status != "proposed" or plan.proposed_by == p.user_id:
        raise HTTPException(409, "Independent approval of proposed plan required")
    plan.approved_by = p.user_id
    plan.status = data.decision
    plan.history = [
        *plan.history,
        {"action": data.decision, "actor": p.user_id, "at": now().isoformat()},
    ]
    emit(db, p, "employee.lifecycle." + data.decision, plan.id)
    return plan


@router.post("/hr/lifecycle/{plan_id}/execute", response_model=LifecycleOutput)
def lifecycle_execute(plan_id: UUID, db: DB, p: HR):
    return execute_lifecycle(db, p, str(plan_id))


@router.post("/finance/costs", response_model=CostOutput, status_code=201)
def cost_create(data: CostInput, db: DB, p: FINANCE_WRITE):
    return record_cost(db, p, data)


@router.get("/finance/costs", response_model=list[CostOutput])
def costs(db: DB, p: FINANCE, limit: Limit = 50, offset: Offset = 0):
    return db.scalars(
        select(CostRecord)
        .where(CostRecord.organization_id == p.organization_id)
        .order_by(CostRecord.id)
        .limit(limit)
        .offset(offset)
    ).all()


@router.post("/finance/budgets", response_model=BudgetOutput, status_code=201)
def budget_create(data: BudgetInput, db: DB, p: FINANCE_WRITE):
    return record_budget(db, p, data)


@router.get("/finance/budget-variance", response_model=list[BudgetVarianceOutput])
def budget_variance_history(
    db: DB,
    p: FINANCE,
    currency: Annotated[str, Query(pattern=r"^[A-Z]{3}$")] = "INR",
    limit: Limit = 50,
    offset: Offset = 0,
):
    audit(db, p, "finance.budget_variance.read", p.organization_id)
    return budget_variances(db, p, currency, limit, offset)


@router.get("/finance/usage", response_model=list[InfrastructureUsageOutput])
def infrastructure_usage(
    db: DB,
    p: FINANCE,
    currency: Annotated[str, Query(pattern=r"^[A-Z]{3}$")] = "INR",
    billing_provider: Literal["aws", "azure", "gcp"] | None = None,
    period: Month | None = None,
    limit: Limit = 50,
    offset: Offset = 0,
):
    scope = [
        CostRecord.organization_id == p.organization_id,
        CostRecord.currency == currency,
        CostRecord.category.in_(["cloud", "infrastructure"]),
        CostRecord.usage_quantity.is_not(None),
    ]
    if billing_provider is not None:
        scope.append(CostRecord.billing_provider == billing_provider)
    if period is not None:
        scope.append(CostRecord.period == period)
    rows = db.execute(
        select(
            CostRecord.period,
            CostRecord.billing_provider,
            CostRecord.usage_unit,
            func.sum(CostRecord.usage_quantity),
            func.sum(CostRecord.amount),
        )
        .where(*scope)
        .group_by(CostRecord.period, CostRecord.billing_provider, CostRecord.usage_unit)
        .order_by(
            CostRecord.period, func.coalesce(CostRecord.billing_provider, ""), CostRecord.usage_unit
        )
        .limit(limit)
        .offset(offset)
    ).all()
    audit(db, p, "finance.usage.read", p.organization_id)
    return [
        {
            "period": month,
            "currency": currency,
            "billing_provider": provider,
            "usage_unit": unit,
            "quantity": quantity,
            "recorded_cost": amount,
        }
        for month, provider, unit, quantity, amount in rows
    ]


@router.get("/finance/summary", response_model=FinanceSummary)
def finance_summary(
    db: DB, p: FINANCE, currency: Annotated[str, Query(pattern=r"^[A-Z]{3}$")] = "INR"
):
    audit(db, p, "finance.summary.read", p.organization_id)
    return summarize(db, p, currency)


@router.get("/finance/what-if")
def finance_what_if(
    db: DB,
    p: FINANCE,
    currency: Annotated[str, Query(pattern=r"^[A-Z]{3}$")] = "INR",
    change_percent: Annotated[Decimal, Query(ge=-100, le=1000)] = Decimal(0),
) -> dict[str, str]:
    total = summarize(db, p, currency).total
    return {
        "currency": currency,
        "historical_total": str(total),
        "scenario_total": str((total * (1 + change_percent / 100)).quantize(Decimal("0.01"))),
        "source": "deterministic proportional scenario; no live billing",
    }


@router.post("/projects/{project_id}/members", response_model=MemberOutput, status_code=201)
def project_member_add(project_id: UUID, data: MemberInput, db: DB, p: P):
    if p.role != "owner":
        p.require("task.manage")
        project_access(db, p, str(project_id), manager=True)
    else:
        project_access(db, p, str(project_id))
    member = active_developer(db, p, str(data.user_id))
    if data.manager and member.role != "senior_developer":
        raise HTTPException(422, "Only senior developers may manage a project")
    record = ProjectMember(
        id=identifier(),
        organization_id=p.organization_id,
        project_id=str(project_id),
        user_id=member.user_id,
        manager=data.manager,
    )
    db.add(record)
    emit(db, p, "project.member.added", record.id)
    return record


@router.post("/projects/{project_id}/sprints", response_model=SprintOutput, status_code=201)
def sprint_create(project_id: UUID, data: SprintInput, db: DB, p: P):
    p.require("task.manage")
    project_access(db, p, str(project_id), manager=True)
    record = Sprint(
        id=identifier(),
        organization_id=p.organization_id,
        project_id=str(project_id),
        **data.model_dump(),
    )
    db.add(record)
    db.flush()
    emit(db, p, "sprint.created", record.id)
    return record


@router.post("/projects/{project_id}/comments", response_model=CommentOutput, status_code=201)
def comment_create(project_id: UUID, data: CommentInput, db: DB, p: P):
    project_access(db, p, str(project_id))
    record = ProjectComment(
        id=identifier(),
        organization_id=p.organization_id,
        project_id=str(project_id),
        author_id=p.user_id,
        body=data.body,
    )
    db.add(record)
    emit(db, p, "project.comment.created", record.id)
    return record


@router.get("/projects/{project_id}/comments", response_model=list[CommentOutput])
def comments(project_id: UUID, db: DB, p: P, limit: Limit = 50, offset: Offset = 0):
    project_access(db, p, str(project_id))
    return db.scalars(
        select(ProjectComment)
        .where(
            ProjectComment.organization_id == p.organization_id,
            ProjectComment.project_id == str(project_id),
        )
        .order_by(ProjectComment.created_at, ProjectComment.id)
        .limit(limit)
        .offset(offset)
    ).all()


@router.get("/projects/{project_id}/tasks", response_model=list[TaskOutput])
def tasks(project_id: UUID, db: DB, p: P, limit: Limit = 50, offset: Offset = 0):
    project_access(db, p, str(project_id))
    return db.scalars(
        select(Task)
        .where(Task.organization_id == p.organization_id, Task.project_id == str(project_id))
        .order_by(Task.id)
        .limit(limit)
        .offset(offset)
    ).all()


@router.patch("/tasks/{task_id}", response_model=TaskOutput)
def task_update(task_id: UUID, data: TaskUpdate, db: DB, p: P):
    task = scoped(db, Task, p, str(task_id), lock=True)
    project_access(db, p, task.project_id)
    manager = data.status == "done" or any(
        value is not None for value in (data.priority, data.deadline, data.sprint_id)
    )
    if manager or task.assignee_id != p.user_id:
        p.require("task.manage")
        project_access(db, p, task.project_id, manager=True)
    transitions = {
        "todo": {"in_progress"},
        "in_progress": {"review"},
        "review": {"done", "in_progress"},
        "done": set(),
    }
    if data.status != task.status and data.status not in transitions.get(task.status, set()):
        raise HTTPException(409, "Invalid task transition")
    detail = db.scalar(
        select(TaskDetail).where(
            TaskDetail.organization_id == p.organization_id, TaskDetail.task_id == task.id
        )
    )
    if detail is None:
        detail = TaskDetail(organization_id=p.organization_id, task_id=task.id)
        db.add(detail)
    if data.sprint_id:
        sprint = scoped(db, Sprint, p, str(data.sprint_id))
        if sprint.project_id != task.project_id:
            raise HTTPException(422, "Sprint belongs to another project")
        detail.sprint_id = sprint.id
    if data.priority:
        detail.priority = data.priority
    if data.deadline:
        if data.deadline.tzinfo is None:
            raise HTTPException(422, "Deadline requires timezone")
        detail.deadline = data.deadline
    task.status = data.status
    emit(db, p, "task.updated", task.id)
    return task
