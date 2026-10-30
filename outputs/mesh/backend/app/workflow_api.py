from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException
from pydantic import Field
from sqlalchemy import select

from app.api import DB, Limit, Offset, P
from app.devtrack import project_access
from app.enterprise_api import HR, OWNER
from app.enterprise_schemas import ComplaintOutput, LifecycleInput, LifecycleOutput, SprintOutput
from app.hr import propose_lifecycle
from app.models import Complaint, Employee, LifecyclePlan, Membership, Sprint, Task, TaskDetail, now
from app.provisioning import activate_provisioned_scim, cancel_provisioning, reconcile_provisioning
from app.rehire import (
    RehireAbort,
    RehireActivation,
    abort_rehire,
    activate_rehire,
    request_scim_restoration,
)
from app.schemas import Input
from app.services import emit, scoped

router = APIRouter(prefix="/api/v1")


class ComplaintStatus(Input):
    status: Literal["investigating", "resolved"]


class SprintStatus(Input):
    status: Literal["active", "completed"]


class Confirmation(Input):
    reference: Annotated[str, Field(min_length=8, max_length=200)]


class ProvisioningActivation(Input):
    reference: Annotated[str, Field(min_length=8, max_length=200)]
    external_activation_approved: Literal[True]


class ProvisioningCancellation(Input):
    reference: Annotated[str, Field(min_length=8, max_length=200)]
    external_access_revoked: Literal[True]


class CancellationInput(Input):
    reason: Annotated[str, Field(min_length=8, max_length=1000)]


@router.post(
    "/hr/lifecycle/{plan_id}/compensation", response_model=LifecycleOutput, status_code=201
)
def lifecycle_compensation(plan_id: UUID, data: CancellationInput, db: DB, p: HR):
    """Propose an inverse plan; execution still needs fresh independent approval."""
    source = scoped(db, LifecyclePlan, p, str(plan_id), lock=True)
    if source.status != "completed" or source.kind in {"offboarding", "rehire"}:
        raise HTTPException(
            409,
            "Only completed non-offboarding changes can generate an inverse plan; revoked access requires separate rehire review",
        )
    previous = next(
        (item for item in source.history if item.get("action") == "compensation_proposed"), None
    )
    if previous:
        return scoped(db, LifecyclePlan, p, previous["compensation_plan_id"])
    employee = scoped(db, Employee, p, source.employee_id, lock=True)
    member = db.get(Membership, (p.organization_id, employee.user_id), with_for_update=True)
    expected = {
        **source.snapshot,
        "role": (source.proposed.get("role") or source.snapshot["role"])
        if source.kind != "onboarding"
        else source.snapshot["role"],
        "department": (source.proposed.get("department") or source.snapshot["department"])
        if source.kind != "onboarding"
        else source.snapshot["department"],
        "status": "active" if source.kind == "onboarding" else source.snapshot["status"],
    }
    current = (
        {
            "active": member.active,
            "role": member.role,
            "department": employee.department,
            "status": employee.status,
        }
        if member
        else {}
    )
    if current != expected or not current.get("active"):
        raise HTTPException(
            409,
            "Access changed after execution; an explicitly reviewed replacement plan is required",
        )
    kind: Literal["offboarding", "role_change"] = (
        "offboarding" if source.kind == "onboarding" else "role_change"
    )
    plan = propose_lifecycle(
        db,
        p,
        LifecycleInput(
            employee_id=UUID(employee.id),
            kind=kind,
            role=source.snapshot["role"] if kind == "role_change" else None,
            department=source.snapshot["department"] if kind == "role_change" else None,
        ),
    )
    plan.history = [
        *plan.history,
        {
            "action": "compensates",
            "source_plan_id": source.id,
            "reason": data.reason,
            "actor": p.user_id,
            "at": now().isoformat(),
        },
    ]
    source.history = [
        *source.history,
        {
            "action": "compensation_proposed",
            "compensation_plan_id": plan.id,
            "actor": p.user_id,
            "at": now().isoformat(),
        },
    ]
    emit(db, p, "employee.lifecycle.compensation_proposed", plan.id)
    return plan


@router.post("/hr/lifecycle/{plan_id}/rehire-activation", response_model=LifecycleOutput)
def rehire_activation(plan_id: UUID, data: RehireActivation, db: DB, p: OWNER):
    return activate_rehire(db, p, str(plan_id), data)


@router.post("/hr/lifecycle/{plan_id}/restore-scim", response_model=LifecycleOutput)
def rehire_restore_scim(plan_id: UUID, data: RehireActivation, db: DB, p: OWNER):
    return request_scim_restoration(db, p, str(plan_id), data)


@router.post("/hr/lifecycle/{plan_id}/abort-rehire", response_model=LifecycleOutput)
def rehire_abort(plan_id: UUID, data: RehireAbort, db: DB, p: OWNER):
    return abort_rehire(db, p, str(plan_id), data)


@router.post("/hr/lifecycle/{plan_id}/provision-reconcile", response_model=LifecycleOutput)
def provision_reconcile(plan_id: UUID, data: Confirmation, db: DB, p: OWNER):
    return reconcile_provisioning(db, p, str(plan_id), data.reference)


@router.post("/hr/lifecycle/{plan_id}/activate-provisioned-scim", response_model=LifecycleOutput)
def provision_activate(plan_id: UUID, data: ProvisioningActivation, db: DB, p: OWNER):
    return activate_provisioned_scim(db, p, str(plan_id), data.reference)


@router.post("/hr/lifecycle/{plan_id}/cancel-provisioning", response_model=LifecycleOutput)
def provision_cancel(plan_id: UUID, data: ProvisioningCancellation, db: DB, p: OWNER):
    return cancel_provisioning(db, p, str(plan_id), data.reference)


@router.post("/hr/lifecycle/{plan_id}/cancel", response_model=LifecycleOutput)
def lifecycle_cancel(plan_id: UUID, data: CancellationInput, db: DB, p: OWNER):
    plan = scoped(db, LifecyclePlan, p, str(plan_id), lock=True)
    if plan.status == "cancelled":
        return plan
    if plan.status not in {"proposed", "approved"}:
        raise HTTPException(
            409, "Executed access changes require reconciliation rather than cancellation"
        )
    plan.status = "cancelled"
    plan.history = [
        *plan.history,
        {"action": "cancelled", "actor": p.user_id, "reason": data.reason, "at": now().isoformat()},
    ]
    emit(db, p, "employee.lifecycle.cancelled", plan.id)
    return plan


@router.patch("/hr/complaints/{complaint_id}", response_model=ComplaintOutput)
def complaint_update(complaint_id: UUID, data: ComplaintStatus, db: DB, p: HR):
    complaint = scoped(db, Complaint, p, str(complaint_id), lock=True)
    if complaint.author_id == p.user_id:
        raise HTTPException(403, "Independent complaint handler required")
    if data.status not in {"open": {"investigating"}, "investigating": {"resolved"}}.get(
        complaint.status, set()
    ):
        raise HTTPException(409, "Invalid complaint transition")
    complaint.status = data.status
    emit(db, p, "complaint." + complaint.status, complaint.id)
    return complaint


@router.post("/hr/lifecycle/{plan_id}/reconcile", response_model=LifecycleOutput)
def reconcile(plan_id: UUID, data: Confirmation, db: DB, p: OWNER):
    plan = scoped(db, LifecyclePlan, p, str(plan_id), lock=True)
    if plan.status != "reconciliation_required":
        raise HTTPException(409, "Plan does not require external reconciliation")
    if plan.kind == "rehire":
        raise HTTPException(409, "Use the explicit rehire activation review")
    provisioning = plan.proposed.get("provisioning")
    if provisioning and provisioning.get("state") not in {"verified_inactive", "verified_active"}:
        raise HTTPException(409, "Verify the provisioned account before manual completion")
    employee = scoped(db, Employee, p, plan.employee_id)
    member = db.get(Membership, (p.organization_id, employee.user_id))
    if plan.kind == "offboarding" and (member is None or member.active):
        raise HTTPException(409, "Local access must remain revoked")
    plan.history = [
        *plan.history,
        {
            "action": "external_manual_attestation",
            "actor": p.user_id,
            "reference": data.reference,
            "at": now().isoformat(),
        },
    ]
    plan.proposed = {
        **plan.proposed,
        "integrations": [
            {
                **step,
                "state": "verified_revoked"
                if step["state"] == "verified_revoked"
                else "human_attested",
            }
            for step in plan.proposed["integrations"]
        ],
    }
    plan.status = "completed"
    emit(db, p, "employee.lifecycle.reconciled", plan.id)
    return plan


@router.get("/projects/{project_id}/sprints", response_model=list[SprintOutput])
def sprints(project_id: UUID, db: DB, p: P, limit: Limit = 50, offset: Offset = 0):
    project_access(db, p, str(project_id))
    return db.scalars(
        select(Sprint)
        .where(Sprint.organization_id == p.organization_id, Sprint.project_id == str(project_id))
        .order_by(Sprint.starts_on, Sprint.id)
        .limit(limit)
        .offset(offset)
    ).all()


@router.patch("/sprints/{sprint_id}", response_model=SprintOutput)
def sprint_update(sprint_id: UUID, data: SprintStatus, db: DB, p: P):
    p.require("task.manage")
    sprint = scoped(db, Sprint, p, str(sprint_id), lock=True)
    project_access(db, p, sprint.project_id, manager=True)
    if (sprint.status, data.status) not in {("planned", "active"), ("active", "completed")}:
        raise HTTPException(409, "Invalid sprint transition")
    if data.status == "completed":
        unfinished = db.scalar(
            select(Task.id)
            .join(
                TaskDetail,
                (TaskDetail.organization_id == Task.organization_id)
                & (TaskDetail.task_id == Task.id),
            )
            .where(
                Task.organization_id == p.organization_id,
                TaskDetail.sprint_id == sprint.id,
                Task.status != "done",
            )
            .limit(1)
        )
        if unfinished:
            raise HTTPException(409, "Sprint still contains unfinished tasks")
    sprint.status = data.status
    emit(db, p, "sprint." + sprint.status, sprint.id)
    return sprint


@router.get("/tasks/{task_id}/details")
def task_details(task_id: UUID, db: DB, p: P) -> dict:
    task = scoped(db, Task, p, str(task_id))
    project_access(db, p, task.project_id)
    detail = db.scalar(
        select(TaskDetail).where(
            TaskDetail.organization_id == p.organization_id, TaskDetail.task_id == task.id
        )
    )
    return {
        "id": task.id,
        "priority": detail.priority if detail else "normal",
        "deadline": detail.deadline if detail else None,
        "sprint_id": detail.sprint_id if detail else None,
    }
