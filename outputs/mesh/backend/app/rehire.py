"""Reviewed rehire activation; no automatic external restoration or retained grants."""

from typing import Annotated, Literal, cast

from fastapi import HTTPException
from pydantic import Field
from sqlalchemy import delete, select, text, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.orm import Session

from app.auth import Principal
from app.core.config import settings
from app.core.db import tenant_context
from app.lifecycle_guards import require_reviewed_inventory
from app.models import (
    CloudAssessmentJob,
    Employee,
    LifecyclePlan,
    Membership,
    Organization,
    Outbox,
    ProjectMember,
    ScanJob,
    now,
)
from app.schemas import Input
from app.services import emit, scoped


class RehireActivation(Input):
    reference: Annotated[str, Field(min_length=8, max_length=200)]
    provider_sessions_revoked: Literal[True]
    external_access_reviewed: Literal[True]


class RehireAbort(Input):
    reference: Annotated[str, Field(min_length=8, max_length=200)]
    external_access_revoked: Literal[True]


def review_rehire(
    db: Session, p: Principal, plan_id: str
) -> tuple[LifecyclePlan, Employee | None, Membership | None]:
    p.require("organization.manage")
    plan = scoped(db, LifecyclePlan, p, plan_id, lock=True)
    owner = db.get(
        Membership, (p.organization_id, p.user_id), with_for_update=True, populate_existing=True
    )
    approver = (
        db.get(Membership, (p.organization_id, plan.approved_by), populate_existing=True)
        if plan.approved_by
        else None
    )
    organization = db.get(Organization, p.organization_id, populate_existing=True)
    if (
        not owner
        or not owner.active
        or owner.role != "owner"
        or not organization
        or organization.status != "active"
    ):
        raise HTTPException(403, "Active owner and organization required")
    if plan.kind != "rehire" or plan.proposed_by == p.user_id:
        raise HTTPException(409, "Independent owner review of an explicit rehire plan required")
    if plan.status == "completed":
        return plan, None, None
    if (
        plan.status != "reconciliation_required"
        or plan.proposed.get("activation") != "owner_attestation_required"
    ):
        raise HTTPException(409, "Execute the approved rehire plan before activation review")
    if (
        not approver
        or not approver.active
        or approver.role != "owner"
        or approver.user_id == plan.proposed_by
    ):
        raise HTTPException(409, "Original independent owner approval must remain valid")
    employee = scoped(db, Employee, p, plan.employee_id, lock=True)
    member = db.get(
        Membership,
        (p.organization_id, employee.user_id),
        with_for_update=True,
        populate_existing=True,
    )
    if (
        not member
        or member.active
        or member.role in {"owner", "hr"}
        or employee.verification_status != "approved"
    ):
        raise HTTPException(
            409, "Inactive nonprivileged membership and human identity approval required"
        )
    current = {
        "active": member.active,
        "role": member.role,
        "department": employee.department,
        "status": employee.status,
    }
    if current != plan.snapshot or employee.status != "offboarded":
        raise HTTPException(409, "Employee access changed after review")
    require_reviewed_inventory(db, member, plan.proposed["integrations"])
    return plan, employee, member


def activate_rehire(
    db: Session, p: Principal, plan_id: str, data: RehireActivation
) -> LifecyclePlan:
    plan, employee, member = review_rehire(db, p, plan_id)
    if employee is None or member is None:
        return plan
    role, department = plan.proposed.get("role"), plan.proposed.get("department")
    if (
        role not in {"junior_developer", "senior_developer", "security_analyst"}
        or not isinstance(department, str)
        or not department.strip()
    ):
        raise HTTPException(409, "Explicit nonprivileged role and department required")
    if db.get_bind().dialect.name == "postgresql":
        tenant_context(db, p.organization_id, p.user_id)
        removed = int(
            db.scalar(
                text("SELECT public.mesh_rehire_clear_project_grants(:plan)"), {"plan": plan.id}
            )
            or 0
        )
    else:
        removed = cast(
            CursorResult,
            db.execute(
                delete(ProjectMember).where(
                    ProjectMember.organization_id == p.organization_id,
                    ProjectMember.user_id == member.user_id,
                )
            ),
        ).rowcount
    cancelled = 0
    for model in (ScanJob, CloudAssessmentJob):
        result = db.execute(
            update(model)
            .where(
                model.organization_id == p.organization_id,
                model.requested_by == member.user_id,
                model.status.in_(["queued", "running"]),
            )
            .values(status="cancelled", lease_until=None)
        )
        cancelled += cast(CursorResult, result).rowcount
    member.role, member.active, member.access_not_before = role, True, now()
    employee.department, employee.status = department, "active"
    plan.proposed = {
        **plan.proposed,
        "activation": "human_attested",
        "integrations": [
            {
                **step,
                "state": "verified_restored"
                if step["state"] == "verified_restored"
                else "human_attested_restored",
            }
            for step in plan.proposed["integrations"]
        ],
    }
    plan.status = "completed"
    plan.history = [
        *plan.history,
        {
            "action": "rehire_activated_by_owner_attestation",
            "actor": p.user_id,
            "reference": data.reference,
            "provider_sessions_revoked": True,
            "external_access_reviewed": True,
            "removed_project_grants": removed,
            "cancelled_pre_rehire_jobs": cancelled,
            "at": now().isoformat(),
        },
    ]
    emit(db, p, "employee.rehire.activated", plan.id)
    return plan


def request_scim_restoration(
    db: Session, p: Principal, plan_id: str, data: RehireActivation
) -> LifecyclePlan:
    plan, employee, member = review_rehire(db, p, plan_id)
    if employee is None or member is None:
        return plan
    binding = settings().scim_bindings.get(p.organization_id)
    if binding is None or not binding.allow_activation:
        raise HTTPException(503, "Operator-authorized SCIM activation is not configured")
    steps = [step for step in plan.proposed["integrations"] if step["provider"] == "scim"]
    if not steps:
        raise HTTPException(409, "No reviewed SCIM account is linked to this rehire")
    queued = set()
    for step in steps:
        if step["state"] == "verified_restored":
            continue
        existing = db.scalar(
            select(Outbox).where(
                Outbox.organization_id == p.organization_id,
                Outbox.topic == "lifecycle.scim.restore",
                Outbox.payload["plan_id"].as_string() == plan.id,
                Outbox.payload["account_id"].as_string() == step["id"],
            )
        )
        if existing is not None:
            if existing.status == "dead_letter":
                raise HTTPException(
                    409, "Restoration needs reviewed dead-letter retry or manual reconciliation"
                )
            continue
        db.add(
            Outbox(
                organization_id=p.organization_id,
                topic="lifecycle.scim.restore",
                payload={"plan_id": plan.id, "account_id": step["id"]},
            )
        )
        queued.add(step["id"])
    if not queued:
        return plan
    plan.proposed = {
        **plan.proposed,
        "restoration_request": {
            "actor": p.user_id,
            "reference": data.reference,
            "provider_sessions_revoked": True,
        },
        "integrations": [
            {**step, "state": "queued_restoration"} if step["id"] in queued else step
            for step in plan.proposed["integrations"]
        ],
    }
    plan.history = [
        *plan.history,
        {
            "action": "scim_restoration_requested",
            "actor": p.user_id,
            "reference": data.reference,
            "at": now().isoformat(),
        },
    ]
    emit(db, p, "employee.rehire.scim_restoration_requested", plan.id)
    return plan


def abort_rehire(db: Session, p: Principal, plan_id: str, data: RehireAbort) -> LifecyclePlan:
    from app.hr import require_lifecycle_authority

    require_lifecycle_authority(db, p, "organization.manage")
    plan = scoped(db, LifecyclePlan, p, plan_id, lock=True)
    if plan.kind != "rehire" or p.user_id == plan.proposed_by:
        raise HTTPException(409, "Independent owner review of a rehire plan required")
    if plan.status == "cancelled":
        return plan
    if plan.status not in {"proposed", "approved", "reconciliation_required"}:
        raise HTTPException(409, "Completed rehire needs a new offboarding plan")
    employee = scoped(db, Employee, p, plan.employee_id, lock=True)
    member = db.get(
        Membership,
        (p.organization_id, employee.user_id),
        with_for_update=True,
        populate_existing=True,
    )
    if member is None or member.active or employee.status != "offboarded":
        raise HTTPException(409, "Local access must remain revoked before abandoning rehire")
    plan.status = "cancelled"
    plan.history = [
        *plan.history,
        {
            "action": "rehire_aborted_by_owner_attestation",
            "actor": p.user_id,
            "reference": data.reference,
            "external_access_revoked": True,
            "at": now().isoformat(),
        },
    ]
    emit(db, p, "employee.rehire.aborted", plan.id)
    return plan
