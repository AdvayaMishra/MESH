from datetime import timedelta

import pytest
from app import provision_worker
from app.core.config import SCIMBinding, settings
from app.models import (
    Employee,
    IntegrationAccount,
    LifecyclePlan,
    Membership,
    Organization,
    Outbox,
    identifier,
    now,
)
from app.scim_provisioning import ProvisioningSCIMClient
from app.worker import consume
from conftest import DEV, HR, ORG_A, ORG_B, OWNER, headers, login
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker
from test_lifecycle_compensation import approve


@pytest.fixture
def queued(client, db, monkeypatch):
    monkeypatch.setattr(
        settings(),
        "scim_bindings",
        {
            ORG_A: SCIMBinding(
                base_url="https://scim.example.org/v2",
                token="fixture-provisioning-token",
                allow_provisioning=True,
                allow_activation=True,
            )
        },
    )
    monkeypatch.setattr(
        provision_worker, "SessionFactory", sessionmaker(db.get_bind(), expire_on_commit=False)
    )
    employee = Employee(
        organization_id=ORG_A,
        user_id=DEV,
        name="Synthetic onboarding",
        department="Engineering",
        verification_status="approved",
        status="onboarding",
    )
    db.add(employee)
    db.commit()
    login(HR)
    response = client.post(
        "/api/v1/hr/lifecycle",
        headers=headers(),
        json={"employee_id": employee.id, "kind": "onboarding", "provision_scim": True},
    )
    assert response.status_code == 201, response.text
    plan_id = response.json()["id"]
    approve(client, plan_id)
    response = client.post(f"/api/v1/hr/lifecycle/{plan_id}/execute", headers=headers())
    assert response.status_code == 200 and response.json()["status"] == "reconciliation_required", (
        response.text
    )
    message = db.scalar(select(Outbox).where(Outbox.topic == provision_worker.TOPIC))
    assert message is not None
    return employee.id, plan_id, message.id


def retry(db, message_id):
    db.expire_all()
    message = db.get(Outbox, message_id)
    message.available_at = now() - timedelta(seconds=1)
    db.commit()


def test_create_reservation_is_committed_before_post_and_delivery_is_idempotent(
    queued, db, monkeypatch
):
    employee, plan, message = queued
    calls = []
    monkeypatch.setattr(ProvisioningSCIMClient, "find", lambda *args, **kwargs: None)

    def create(self, subject, email):
        with provision_worker.SessionFactory() as other:
            assert other.get(Outbox, message).payload["creation_sent"] is True
        calls.append((subject, email))
        return {"id": "created-user", "active": False}

    monkeypatch.setattr(ProvisioningSCIMClient, "create_inactive", create)
    assert provision_worker.run_once(ORG_B) is False
    assert provision_worker.run_once(ORG_A) is True
    db.expire_all()
    assert db.get(Outbox, message).status == "delivered"
    record = db.get(LifecyclePlan, plan)
    assert record.proposed["provisioning"]["state"] == "verified_inactive"
    assert record.status == "reconciliation_required"
    assert db.query(IntegrationAccount).filter_by(organization_id=ORG_A, user_id=DEV).count() == 1
    assert provision_worker.run_once(ORG_A) is False and len(calls) == 1


def test_lost_post_response_is_recovered_by_discovery_without_a_second_create(
    queued, db, monkeypatch
):
    _, plan, message = queued
    remote = None
    creates = []

    def create(*args):
        nonlocal remote
        creates.append(True)
        remote = {"id": "created-before-timeout", "active": False}
        raise HTTPException(503, "Lost response")

    monkeypatch.setattr(ProvisioningSCIMClient, "find", lambda *args, **kwargs: remote)
    monkeypatch.setattr(ProvisioningSCIMClient, "create_inactive", create)
    provision_worker.run_once(ORG_A)
    db.expire_all()
    assert db.get(LifecyclePlan, plan).proposed["provisioning"]["state"] == "creation_uncertain"
    retry(db, message)
    provision_worker.run_once(ORG_A)
    db.expire_all()
    assert len(creates) == 1 and db.get(Outbox, message).status == "delivered"


def test_ambiguous_create_is_never_repeated_and_stops_at_five_attempts(queued, db, monkeypatch):
    _, plan, message = queued
    calls = []
    monkeypatch.setattr(ProvisioningSCIMClient, "find", lambda *args, **kwargs: None)

    def fail(*args):
        calls.append(True)
        raise HTTPException(503, "Uncertain response")

    monkeypatch.setattr(ProvisioningSCIMClient, "create_inactive", fail)
    for _ in range(5):
        retry(db, message)
        provision_worker.run_once(ORG_A)
    db.expire_all()
    assert calls == [True]
    assert db.get(Outbox, message).status == "dead_letter" and db.get(Outbox, message).attempts == 5
    assert db.get(LifecyclePlan, plan).proposed["provisioning"]["state"] == "manual_review_required"
    assert db.query(IntegrationAccount).filter_by(organization_id=ORG_A, user_id=DEV).count() == 0


def test_crash_after_reservation_and_stale_lease_do_not_repeat_post_or_commit_output(
    queued, db, monkeypatch
):
    _, _, message = queued
    first = provision_worker.claim_one(ORG_A)
    assert first is not None and provision_worker.reserve_post(first)
    retry(db, message)
    second = provision_worker.claim_one(ORG_A)
    assert second is not None
    assert not provision_worker.reserve_post(first) and not provision_worker.reserve_post(second)
    provision_worker.finish(first, {"id": "stale-worker-user", "active": False})
    db.expire_all()
    assert db.query(IntegrationAccount).filter_by(organization_id=ORG_A, user_id=DEV).count() == 0


@pytest.mark.parametrize(
    "change",
    ["owner", "hr", "membership", "identity", "suspension", "email", "authority", "inventory"],
)
def test_provisioning_rechecks_reviewed_authority_before_any_provider_call(
    queued, db, monkeypatch, change
):
    employee, _, _ = queued
    if change == "owner":
        db.get(Membership, (ORG_A, OWNER)).role = "junior_developer"
    elif change == "hr":
        db.get(Membership, (ORG_A, HR)).active = False
    elif change == "membership":
        db.get(Membership, (ORG_A, DEV)).active = False
    elif change == "identity":
        db.get(Employee, employee).verification_status = "rejected"
    elif change == "suspension":
        db.get(Organization, ORG_A).status = "suspended"
    elif change == "email":
        db.get(Membership, (ORG_A, DEV)).email = "changed@example.invalid"
    elif change == "authority":
        monkeypatch.setattr(
            settings(),
            "scim_bindings",
            {
                ORG_A: SCIMBinding(
                    base_url="https://different.example.invalid/v2",
                    token="fixture-provisioning-token",
                    allow_provisioning=True,
                )
            },
        )
    else:
        db.add(
            IntegrationAccount(
                organization_id=ORG_A,
                user_id=DEV,
                provider="manual",
                external_id="new-unreviewed-account",
            )
        )
    db.commit()
    calls = []
    monkeypatch.setattr(ProvisioningSCIMClient, "find", lambda *args, **kwargs: calls.append(True))
    provision_worker.run_once(ORG_A)
    assert calls == []


def test_a_prior_cancelled_creation_intent_prevents_automatic_duplicate_creation(
    queued, db, monkeypatch
):
    _, _, message = queued
    current = db.get(Outbox, message)
    db.add(
        Outbox(
            organization_id=ORG_A,
            topic=provision_worker.TOPIC,
            status="cancelled",
            payload={
                "plan_id": identifier(),
                "subject": current.payload["subject"],
                "creation_sent": True,
            },
        )
    )
    db.commit()
    calls = []
    monkeypatch.setattr(ProvisioningSCIMClient, "find", lambda *args, **kwargs: None)
    monkeypatch.setattr(ProvisioningSCIMClient, "create_inactive", lambda *args: calls.append(True))
    provision_worker.run_once(ORG_A)
    db.expire_all()
    assert calls == [] and db.get(Outbox, message).payload["creation_sent"] is True


def test_generic_outbox_consumer_never_falsely_delivers_provisioning(queued, db):
    _, _, message = queued
    consume(db, ORG_A)
    db.commit()
    assert db.get(Outbox, message).status == "pending"


def test_owner_can_verify_an_uncertain_account_then_activate_with_separate_approval(
    queued, client, db, monkeypatch
):
    _, plan, message = queued
    active = False
    monkeypatch.setattr(
        ProvisioningSCIMClient,
        "find",
        lambda *args, **kwargs: {"id": "manual-discovery-user", "active": active},
    )
    login(OWNER)
    base = f"/api/v1/hr/lifecycle/{plan}"
    assert (
        client.post(
            base + "/reconcile",
            headers=headers(),
            json={"reference": "cannot-skip-provision-verification"},
        ).status_code
        == 409
    )
    result = client.post(
        base + "/provision-reconcile",
        headers=headers(),
        json={"reference": "verified-discovery-ticket"},
    )
    assert result.status_code == 200, result.text
    assert result.json()["proposed"]["provisioning"]["state"] == "verified_inactive"
    db.expire_all()
    assert db.get(Outbox, message).status == "delivered"
    assert (
        client.post(
            base + "/activate-provisioned-scim",
            headers=headers(),
            json={"reference": "activation-ticket", "external_activation_approved": False},
        ).status_code
        == 422
    )

    def restore(*args):
        nonlocal active
        active = True

    monkeypatch.setattr(ProvisioningSCIMClient, "restore", restore)
    monkeypatch.setattr(
        ProvisioningSCIMClient,
        "confirmed",
        lambda *args, **kwargs: {"id": "manual-discovery-user", "active": active},
    )
    result = client.post(
        base + "/activate-provisioned-scim",
        headers=headers(),
        json={"reference": "activation-ticket", "external_activation_approved": True},
    )
    assert result.status_code == 200, result.text
    assert result.json()["status"] == "completed"
    assert result.json()["proposed"]["provisioning"]["state"] == "verified_active"


def test_cancel_external_provisioning_keeps_local_access_and_fences_pending_work(
    queued, client, db, monkeypatch
):
    _, plan, message = queued
    login(OWNER)
    result = client.post(
        f"/api/v1/hr/lifecycle/{plan}/cancel-provisioning",
        headers=headers(),
        json={"reference": "external-cleanup-ticket", "external_access_revoked": True},
    )
    assert result.status_code == 200 and result.json()["status"] == "cancelled", result.text
    db.expire_all()
    assert db.get(Outbox, message).status == "cancelled" and db.get(Membership, (ORG_A, DEV)).active
    calls = []
    monkeypatch.setattr(ProvisioningSCIMClient, "find", lambda *args, **kwargs: calls.append(True))
    assert not provision_worker.run_once(ORG_A) and calls == []
