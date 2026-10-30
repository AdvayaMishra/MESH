"""Reviewed onboarding intents and verified linkage of inactive SCIM accounts."""

import hashlib
import json

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import Principal
from app.core.config import settings
from app.lifecycle_guards import account_review, require_reviewed_inventory
from app.models import Employee, IntegrationAccount, LifecyclePlan, Membership, Organization, now
from app.services import emit, scoped


def provisioning_intent(member: Membership, employee_id: str) -> dict:
    binding = settings().scim_bindings.get(member.organization_id)
    if binding is None or not binding.allow_provisioning:
        raise HTTPException(503, "Operator-authorized SCIM provisioning is not configured")
    subject = "mesh:" + member.organization_id + ":" + employee_id
    value = {
        "organization": member.organization_id,
        "user": member.user_id,
        "email": member.email.strip().lower(),
        "authority": binding.base_url,
        "subject": subject,
    }
    return {
        "subject": subject,
        "review_digest": hashlib.sha256(
            json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest(),
        "state": "proposed",
    }


def provisioning_context(
    db: Session, organization: str, plan_id: str
) -> tuple[LifecyclePlan, Employee, Membership, dict]:
    worker = Principal("provisioning-worker", organization, "system")
    plan = scoped(db, LifecyclePlan, worker, plan_id, lock=True)
    if plan.kind != "onboarding" or plan.status != "reconciliation_required":
        raise HTTPException(409, "Approved onboarding provisioning intent required")
    org = db.get(Organization, organization, populate_existing=True)
    approver = (
        db.get(Membership, (organization, plan.approved_by), populate_existing=True)
        if plan.approved_by
        else None
    )
    proposer = db.get(Membership, (organization, plan.proposed_by), populate_existing=True)
    if (
        not org
        or org.status != "active"
        or not approver
        or not approver.active
        or approver.role != "owner"
        or plan.proposed_by == plan.approved_by
        or not proposer
        or not proposer.active
        or proposer.role != "hr"
    ):
        raise HTTPException(409, "Current independent owner and HR authority required")
    employee = scoped(db, Employee, worker, plan.employee_id, lock=True)
    member = db.get(
        Membership, (organization, employee.user_id), with_for_update=True, populate_existing=True
    )
    if (
        not member
        or not member.active
        or member.role in {"owner", "hr"}
        or employee.status != "active"
        or employee.verification_status != "approved"
    ):
        raise HTTPException(409, "Active human-approved nonprivileged employee required")
    require_reviewed_inventory(db, member, plan.proposed["integrations"])
    intent = plan.proposed.get("provisioning")
    expected = provisioning_intent(member, employee.id)
    if not isinstance(intent, dict) or any(
        intent.get(key) != expected[key] for key in ("subject", "review_digest")
    ):
        raise HTTPException(409, "Provisioning identity or authority changed after review")
    return plan, employee, member, intent


def record_provisioned_account(
    db: Session,
    plan: LifecyclePlan,
    employee: Employee,
    member: Membership,
    intent: dict,
    resource: dict,
    actor: Principal,
    *,
    allow_active: bool = False,
) -> IntegrationAccount:
    if (
        type(resource.get("active")) is not bool
        or (resource["active"] and not allow_active)
        or not isinstance(resource.get("id"), str)
    ):
        raise HTTPException(409, "A verified inactive account is required")
    if allow_active:
        actor.require("organization.manage")
    accounts = db.scalars(
        select(IntegrationAccount).where(
            IntegrationAccount.organization_id == member.organization_id,
            IntegrationAccount.provider == "scim",
            (IntegrationAccount.user_id == member.user_id)
            | (IntegrationAccount.external_id == resource["id"]),
        )
    ).all()
    if len(accounts) > 1 or (
        accounts
        and (accounts[0].user_id != member.user_id or accounts[0].external_id != resource["id"])
    ):
        raise HTTPException(409, "External identity is already bound to another reviewed account")
    account = (
        accounts[0]
        if accounts
        else IntegrationAccount(
            organization_id=member.organization_id,
            user_id=member.user_id,
            provider="scim",
            external_id=resource["id"],
        )
    )
    if not accounts:
        db.add(account)
        db.flush()
    step = {
        **account_review(account, member),
        "state": "verified_provisioned_active"
        if resource["active"]
        else "verified_provisioned_inactive",
        "compensation": "manual_review_only",
    }
    previous = [item for item in plan.proposed["integrations"] if item["id"] != account.id]
    plan.proposed = {
        **plan.proposed,
        "integrations": [*previous, step],
        "provisioning": {
            **intent,
            "account_id": account.id,
            "state": "verified_active" if resource["active"] else "verified_inactive",
        },
    }
    plan.history = [
        *plan.history,
        {
            "action": "external_account_verified_active"
            if resource["active"]
            else "external_account_verified_inactive",
            "provider": "scim",
            "account_id": account.id,
            "actor": actor.user_id,
            "at": now().isoformat(),
        },
    ]
    emit(
        db,
        actor,
        "employee.external_provisioning.verified_active"
        if resource["active"]
        else "employee.external_provisioning.verified_inactive",
        plan.id,
    )
    return account


def settle_provision_messages(db: Session, plan: LifecyclePlan, status: str) -> None:
    from sqlalchemy import update

    from app.models import Outbox

    db.execute(
        update(Outbox)
        .where(
            Outbox.organization_id == plan.organization_id,
            Outbox.topic == "lifecycle.scim.provision",
            Outbox.payload["plan_id"].as_string() == plan.id,
            Outbox.status.in_(["pending", "dead_letter"]),
        )
        .values(status=status)
    )


def reconcile_provisioning(
    db: Session, p: Principal, plan_id: str, reference: str
) -> LifecyclePlan:
    from app.hr import require_lifecycle_authority
    from app.scim_provisioning import ProvisioningSCIMClient

    require_lifecycle_authority(db, p, "organization.manage")
    completed = scoped(db, LifecyclePlan, p, plan_id, lock=True)
    if (
        completed.kind == "onboarding"
        and completed.status == "completed"
        and completed.proposed.get("provisioning", {}).get("state") == "verified_active"
        and completed.proposed_by != p.user_id
    ):
        return completed
    plan, employee, member, intent = provisioning_context(db, p.organization_id, plan_id)
    if plan.proposed_by == p.user_id:
        raise HTTPException(409, "Independent owner provisioning review required")
    resource = ProvisioningSCIMClient(p.organization_id).find(
        intent["subject"], member.email, inactive=False
    )
    if resource is None:
        raise HTTPException(
            409, "No uniquely matching external account was found; creation is not repeated"
        )
    record_provisioned_account(db, plan, employee, member, intent, resource, p, allow_active=True)
    settle_provision_messages(db, plan, "delivered")
    plan.history = [
        *plan.history,
        {
            "action": "provisioning_reconciled_by_owner",
            "actor": p.user_id,
            "reference": reference,
            "at": now().isoformat(),
        },
    ]
    if resource["active"] and all(
        step["state"] in {"verified_provisioned_active", "human_attested"}
        for step in plan.proposed["integrations"]
    ):
        plan.status = "completed"
    emit(db, p, "employee.provisioning.reconciled", plan.id)
    return plan


def activate_provisioned_scim(
    db: Session, p: Principal, plan_id: str, reference: str
) -> LifecyclePlan:
    from app.hr import require_lifecycle_authority
    from app.scim_provisioning import ProvisioningSCIMClient

    require_lifecycle_authority(db, p, "organization.manage")
    completed = scoped(db, LifecyclePlan, p, plan_id, lock=True)
    if (
        completed.kind == "onboarding"
        and completed.status == "completed"
        and completed.proposed.get("provisioning", {}).get("state") == "verified_active"
        and completed.proposed_by != p.user_id
    ):
        return completed
    plan, employee, member, intent = provisioning_context(db, p.organization_id, plan_id)
    if plan.proposed_by == p.user_id or intent.get("state") != "verified_inactive":
        raise HTTPException(
            409, "Independent owner activation of a verified inactive account required"
        )
    account = scoped(db, IntegrationAccount, p, intent["account_id"])
    if account.provider != "scim" or account.user_id != member.user_id:
        raise HTTPException(409, "Provisioned account is not bound to this employee")
    client = ProvisioningSCIMClient(p.organization_id)
    client.confirmed(account.external_id, member.email, intent["subject"], inactive=False)
    client.restore(account.external_id, member.email)
    resource = client.confirmed(
        account.external_id, member.email, intent["subject"], inactive=False
    )
    if resource["active"] is not True:
        raise HTTPException(503, "External activation has not been verified")
    record_provisioned_account(db, plan, employee, member, intent, resource, p, allow_active=True)
    if all(
        step["state"] in {"verified_provisioned_active", "human_attested"}
        for step in plan.proposed["integrations"]
    ):
        plan.status = "completed"
    plan.history = [
        *plan.history,
        {
            "action": "provisioned_account_activation_verified",
            "actor": p.user_id,
            "reference": reference,
            "at": now().isoformat(),
        },
    ]
    emit(db, p, "employee.provisioning.activation_verified", plan.id)
    return plan


def cancel_provisioning(db: Session, p: Principal, plan_id: str, reference: str) -> LifecyclePlan:
    from app.hr import require_lifecycle_authority

    require_lifecycle_authority(db, p, "organization.manage")
    plan = scoped(db, LifecyclePlan, p, plan_id, lock=True)
    if (
        plan.kind != "onboarding"
        or not plan.proposed.get("provisioning")
        or plan.proposed_by == p.user_id
    ):
        raise HTTPException(409, "Independent owner review of a provisioning plan required")
    if plan.status == "cancelled":
        return plan
    if plan.status not in {"proposed", "approved", "reconciliation_required"}:
        raise HTTPException(409, "Completed provisioning requires a new reviewed lifecycle plan")
    settle_provision_messages(db, plan, "cancelled")
    plan.status = "cancelled"
    plan.proposed = {
        **plan.proposed,
        "provisioning": {
            **plan.proposed["provisioning"],
            "state": "cancelled_external_revocation_human_attested",
        },
    }
    plan.history = [
        *plan.history,
        {
            "action": "external_provisioning_cancelled",
            "actor": p.user_id,
            "reference": reference,
            "external_access_revoked": True,
            "local_access_unchanged": True,
            "at": now().isoformat(),
        },
    ]
    emit(db, p, "employee.provisioning.cancelled", plan.id)
    return plan
