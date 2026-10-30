"""Two-phase inactive SCIM provisioning with a durable, never-repeated POST intent."""

from dataclasses import dataclass
from datetime import timedelta
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import Principal
from app.core.db import SessionFactory, assert_runtime_role, tenant_context
from app.models import Delivery, LifecyclePlan, Outbox, now
from app.provisioning import provisioning_context, record_provisioned_account
from app.scim_provisioning import ProvisioningSCIMClient
from app.services import emit, lock_tenant, scoped

TOPIC = "lifecycle.scim.provision"
CONSUMER = "scim-inactive-provisioning-v1"


@dataclass(frozen=True)
class Claim:
    organization_id: str
    message_id: str
    plan_id: str
    lease: str


def claimed(db: Session, claim: Claim) -> Outbox | None:
    message = db.scalar(
        select(Outbox)
        .where(Outbox.organization_id == claim.organization_id, Outbox.id == claim.message_id)
        .with_for_update()
    )
    if (
        message is None
        or message.status != "pending"
        or message.payload.get("lease") != claim.lease
    ):
        return None
    return message


def claim_one(organization: str) -> Claim | None:
    with SessionFactory.begin() as db:
        assert_runtime_role(db)
        tenant_context(db, organization, "provisioning-worker")
        if lock_tenant(db, organization) is None:
            return None
        message = db.scalar(
            select(Outbox)
            .where(
                Outbox.organization_id == organization,
                Outbox.topic == TOPIC,
                Outbox.status == "pending",
                Outbox.available_at <= now(),
            )
            .order_by(Outbox.created_at, Outbox.id)
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        if message is None:
            return None
        plan = scoped(
            db,
            LifecyclePlan,
            Principal("provisioning-worker", organization, "system"),
            message.payload["plan_id"],
            lock=True,
        )
        if plan.status in {"completed", "cancelled", "rejected"}:
            message.status = "delivered"
            return None
        if message.attempts >= 5:
            message.status = "dead_letter"
            plan.proposed = {
                **plan.proposed,
                "provisioning": {
                    **plan.proposed.get("provisioning", {}),
                    "state": "manual_review_required",
                },
            }
            emit(
                db,
                Principal("provisioning-worker", organization, "system"),
                "employee.provisioning.manual_review_required",
                plan.id,
            )
            return None
        lease = str(uuid4())
        message.attempts += 1
        message.available_at = now() + timedelta(seconds=180)
        message.payload = {**message.payload, "lease": lease}
        return Claim(organization, message.id, plan.id, lease)


def context(claim: Claim) -> tuple[str, str]:
    with SessionFactory.begin() as db:
        tenant_context(db, claim.organization_id, "provisioning-worker")
        lock_tenant(db, claim.organization_id)
        if claimed(db, claim) is None:
            raise RuntimeError("Provisioning lease changed")
        _, _, member, intent = provisioning_context(db, claim.organization_id, claim.plan_id)
        return member.email, intent["subject"]


def reserve_post(claim: Claim) -> bool:
    with SessionFactory.begin() as db:
        tenant_context(db, claim.organization_id, "provisioning-worker")
        lock_tenant(db, claim.organization_id)
        message = claimed(db, claim)
        if message is None:
            return False
        plan, _, _, intent = provisioning_context(db, claim.organization_id, claim.plan_id)
        previous = db.scalar(
            select(Outbox.id)
            .where(
                Outbox.organization_id == claim.organization_id,
                Outbox.topic == TOPIC,
                Outbox.payload["subject"].as_string() == intent["subject"],
                Outbox.payload["creation_sent"].as_boolean().is_(True),
            )
            .limit(1)
        )
        message.payload = {**message.payload, "creation_sent": True}
        plan.proposed = {**plan.proposed, "provisioning": {**intent, "state": "creation_reserved"}}
        # Commit this intent before HTTP. Even a crash before sending requires discovery/manual review.
        return previous is None


def finish(claim: Claim, resource: dict) -> None:
    with SessionFactory.begin() as db:
        tenant_context(db, claim.organization_id, "provisioning-worker")
        lock_tenant(db, claim.organization_id)
        message = claimed(db, claim)
        if message is None:
            return
        plan, employee, member, intent = provisioning_context(
            db, claim.organization_id, claim.plan_id
        )
        record_provisioned_account(
            db,
            plan,
            employee,
            member,
            intent,
            resource,
            Principal("provisioning-worker", claim.organization_id, "system"),
        )
        db.add(
            Delivery(
                organization_id=claim.organization_id, message_id=message.id, consumer=CONSUMER
            )
        )
        message.status = "delivered"


def fail(claim: Claim) -> None:
    with SessionFactory.begin() as db:
        tenant_context(db, claim.organization_id, "provisioning-worker")
        lock_tenant(db, claim.organization_id)
        message = claimed(db, claim)
        if message is None:
            return
        terminal = message.attempts >= 5
        message.status = "dead_letter" if terminal else "pending"
        message.available_at = now() + timedelta(seconds=min(300, 2**message.attempts))
        plan = scoped(
            db,
            LifecyclePlan,
            Principal("provisioning-worker", claim.organization_id, "system"),
            claim.plan_id,
            lock=True,
        )
        state = (
            "manual_review_required"
            if terminal
            else "creation_uncertain"
            if message.payload.get("creation_sent")
            else "retrying_discovery"
        )
        if plan.status == "reconciliation_required":
            plan.proposed = {
                **plan.proposed,
                "provisioning": {**plan.proposed.get("provisioning", {}), "state": state},
            }
        plan.history = [
            *plan.history,
            {
                "action": "provisioning_" + state,
                "actor": "provisioning-worker",
                "at": now().isoformat(),
            },
        ]
        emit(
            db,
            Principal("provisioning-worker", claim.organization_id, "system"),
            "employee.provisioning." + state,
            plan.id,
        )


def run_once(organization: str) -> bool:
    claim = claim_one(organization)
    if claim is None:
        return False
    try:
        email, subject = context(claim)
        client = ProvisioningSCIMClient(organization)
        resource = client.find(subject, email)
        if resource is None:
            if not reserve_post(claim):
                raise RuntimeError("A create was already reserved; never repeat it automatically")
            resource = client.create_inactive(subject, email)
        finish(claim, resource)
    except Exception:
        fail(claim)
    return True
