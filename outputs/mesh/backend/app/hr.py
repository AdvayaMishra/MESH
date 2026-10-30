from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import Principal
from app.core.config import settings
from app.enterprise_schemas import LeaveInput, LifecycleInput
from app.leave_policy import require_capacity
from app.lifecycle_guards import account_inventory, require_reviewed_inventory
from app.models import (
    Employee,
    LeaveRequest,
    LifecyclePlan,
    Membership,
    Organization,
    Outbox,
    identifier,
    now,
)
from app.services import emit, lock_tenant, scoped


def request_leave(db: Session, p: Principal, data: LeaveInput) -> LeaveRequest:
    employee = scoped(db, Employee, p, str(data.employee_id), lock=True)
    if employee.user_id != p.user_id:
        p.require("employee.write")
    if employee.status == "offboarded":
        raise HTTPException(409, "Employee is offboarded")
    require_capacity(db, p.organization_id, employee.id, data.starts_on, data.ends_on)
    overlap = db.scalar(
        select(LeaveRequest).where(
            LeaveRequest.organization_id == p.organization_id,
            LeaveRequest.employee_id == employee.id,
            LeaveRequest.status.in_(["pending", "approved"]),
            LeaveRequest.starts_on <= data.ends_on,
            LeaveRequest.ends_on >= data.starts_on,
        )
    )
    if overlap:
        raise HTTPException(409, "Overlapping leave request")
    record = LeaveRequest(
        id=identifier(),
        organization_id=p.organization_id,
        employee_id=employee.id,
        **data.model_dump(exclude={"employee_id"}),
    )
    db.add(record)
    db.flush()
    emit(db, p, "leave.requested", record.id)
    return record


def require_lifecycle_authority(
    db: Session, p: Principal, permission: str = "employee.write"
) -> None:
    p.require(permission)
    organization = lock_tenant(db, p.organization_id)
    if organization is not None:
        db.refresh(organization, attribute_names=["status"])
    actor = db.get(
        Membership, (p.organization_id, p.user_id), with_for_update=True, populate_existing=True
    )
    if organization is None or organization.status != "active" or actor is None or not actor.active:
        raise HTTPException(403, "Active lifecycle authority required")
    Principal(actor.user_id, p.organization_id, actor.role).require(permission)


def propose_lifecycle(db: Session, p: Principal, data: LifecycleInput) -> LifecyclePlan:
    require_lifecycle_authority(db, p)
    employee = scoped(db, Employee, p, str(data.employee_id), lock=True)
    member = db.get(Membership, (p.organization_id, employee.user_id))
    if member is None or member.role in {"owner", "hr"}:
        raise HTTPException(403, "Employee lifecycle cannot change privileged memberships")
    if db.scalar(
        select(LifecyclePlan).where(
            LifecyclePlan.organization_id == p.organization_id,
            LifecyclePlan.employee_id == employee.id,
            LifecyclePlan.status.in_(["proposed", "approved", "reconciliation_required"]),
        )
    ):
        raise HTTPException(409, "An unfinished lifecycle plan exists")
    if data.kind in {"promotion", "role_change"} and not data.role:
        raise HTTPException(422, "Target role required")
    if data.kind == "transfer" and not data.department:
        raise HTTPException(422, "Target department required")
    if data.kind == "rehire":
        if (
            member.active
            or employee.status != "offboarded"
            or employee.verification_status != "approved"
        ):
            raise HTTPException(
                409, "Rehire requires an offboarded inactive employee and human identity approval"
            )
        if not data.role or not data.department:
            raise HTTPException(422, "Rehire requires an explicit role and department")
        if not db.scalar(
            select(LifecyclePlan.id)
            .where(
                LifecyclePlan.organization_id == p.organization_id,
                LifecyclePlan.employee_id == employee.id,
                LifecyclePlan.kind == "offboarding",
                LifecyclePlan.status == "completed",
            )
            .limit(1)
        ):
            raise HTTPException(409, "Complete the prior offboarding reconciliation before rehire")
    snapshot = {
        "active": member.active,
        "role": member.role,
        "department": employee.department,
        "status": employee.status,
    }
    proposed: dict = {
        "role": data.role,
        "department": data.department,
        "integrations": [
            {
                **link,
                "state": "pending",
                "compensation": "manual_review_only",
            }
            for link in account_inventory(db, member)
        ],
    }
    if data.provision_scim:
        if data.kind != "onboarding":
            raise HTTPException(422, "SCIM provisioning requires an explicit onboarding plan")
        if any(step["provider"] == "scim" for step in proposed["integrations"]):
            raise HTTPException(409, "SCIM identity is already linked; creation is not required")
        from app.provisioning import provisioning_intent

        proposed["provisioning"] = provisioning_intent(member, employee.id)
    plan = LifecyclePlan(
        id=identifier(),
        organization_id=p.organization_id,
        employee_id=employee.id,
        kind=data.kind,
        snapshot=snapshot,
        proposed=proposed,
        proposed_by=p.user_id,
        history=[{"action": "proposed", "actor": p.user_id, "at": now().isoformat()}],
    )
    db.add(plan)
    db.flush()
    emit(db, p, "employee.lifecycle.proposed", plan.id)
    return plan


def execute_lifecycle(db: Session, p: Principal, plan_id: str) -> LifecyclePlan:
    require_lifecycle_authority(db, p)
    plan = scoped(db, LifecyclePlan, p, plan_id, lock=True)
    if plan.status == "completed":
        return plan
    if plan.status != "approved":
        raise HTTPException(409, "Approved lifecycle plan required")
    approver = db.get(
        Membership,
        (p.organization_id, plan.approved_by),
        with_for_update=True,
        populate_existing=True,
    )
    if (
        approver is None
        or not approver.active
        or approver.role != "owner"
        or plan.approved_by == plan.proposed_by
    ):
        raise HTTPException(409, "Active independent owner approval must remain valid at execution")
    employee = scoped(db, Employee, p, plan.employee_id, lock=True)
    member = db.get(Membership, (p.organization_id, employee.user_id), with_for_update=True)
    organization = db.get(Organization, p.organization_id)
    if member is None or organization is None or organization.status != "active":
        raise HTTPException(409, "Active organization and membership record required")
    current = {
        "active": member.active,
        "role": member.role,
        "department": employee.department,
        "status": employee.status,
    }
    if current != plan.snapshot:
        raise HTTPException(
            409, "Access changed since proposal; create a reviewed replacement plan"
        )
    require_reviewed_inventory(db, member, plan.proposed["integrations"])
    if plan.kind == "offboarding":
        member.access_not_before = now()
        member.active = False
        employee.status = "offboarded"
    elif plan.kind == "rehire":
        if (
            member.active
            or employee.status != "offboarded"
            or employee.verification_status != "approved"
        ):
            raise HTTPException(409, "Rehire identity and revocation prerequisites changed")
        if not plan.proposed.get("role") or not plan.proposed.get("department"):
            raise HTTPException(409, "Explicit reviewed rehire assignments required")
        plan.status = "reconciliation_required"
        plan.proposed = {**plan.proposed, "activation": "owner_attestation_required"}
        plan.history = [
            *plan.history,
            {"action": "rehire_activation_requested", "actor": p.user_id, "at": now().isoformat()},
        ]
        emit(db, p, "employee.rehire.activation_requested", plan.id)
        return plan
    elif plan.kind == "onboarding":
        if employee.verification_status != "approved" or not member.active:
            raise HTTPException(409, "Human ID approval and active authorized membership required")
        employee.status = "active"
    else:
        if not member.active:
            raise HTTPException(409, "Cannot restore revoked access through a lifecycle change")
        if plan.proposed.get("role"):
            member.role = plan.proposed["role"]
        if plan.proposed.get("department"):
            employee.department = plan.proposed["department"]
    # External revocation cannot be faked. Retain local revocation and surface reconciliation.
    steps = []
    for step in plan.proposed["integrations"]:
        queued = (
            plan.kind == "offboarding"
            and step["provider"] == "scim"
            and p.organization_id in settings().scim_bindings
        )
        steps.append({**step, "state": "queued" if queued else "manual_reconciliation_required"})
        if queued:
            db.add(
                Outbox(
                    organization_id=p.organization_id,
                    topic="lifecycle.scim.revoke",
                    payload={"plan_id": plan.id, "account_id": step["id"]},
                )
            )
    plan.proposed = {**plan.proposed, "integrations": steps}
    provisioning = plan.proposed.get("provisioning")
    if provisioning:
        db.add(
            Outbox(
                organization_id=p.organization_id,
                topic="lifecycle.scim.provision",
                payload={
                    "plan_id": plan.id,
                    "subject": provisioning["subject"],
                    "creation_sent": False,
                },
            )
        )
        plan.proposed = {**plan.proposed, "provisioning": {**provisioning, "state": "queued"}}
    plan.status = "reconciliation_required" if steps or provisioning else "completed"
    plan.history = [
        *plan.history,
        {
            "action": "local_access_applied",
            "actor": p.user_id,
            "at": now().isoformat(),
            "external_steps": len(steps),
        },
    ]
    emit(
        db,
        p,
        "employee.offboarded" if plan.kind == "offboarding" else "employee.lifecycle.executed",
        plan.id,
    )
    return plan
