import json

import httpx
import pytest
from app.core.config import SCIMBinding, settings
from app.lifecycle_integrations import SCIMClient
from app.models import Employee, LifecyclePlan, Membership, Organization, Outbox, now
from app.worker import consume
from conftest import DEV, ORG_A, OWNER, headers, login
from fastapi import HTTPException
from sqlalchemy import select
from test_lifecycle_compensation import approve, propose
from test_rehire import activate
from test_scim_lifecycle import configure, prepare_offboarding


def test_scim_activation_is_opt_in_and_verifies_identity_and_final_state(monkeypatch):
    configure(monkeypatch)
    calls = []
    active = False

    def handler(request):
        nonlocal active
        calls.append(request.method)
        if request.method == "PATCH":
            assert json.loads(request.content)["Operations"] == [
                {"op": "replace", "path": "active", "value": True}
            ]
            active = True
            return httpx.Response(204)
        return httpx.Response(
            200,
            json={"id": "user-123", "userName": "employee@example.org", "active": active},
            headers={"ETag": 'W/"fixture-v1"'},
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(HTTPException) as error:
            SCIMClient(ORG_A, client).restore("user-123", "employee@example.org")
        assert error.value.status_code == 503 and calls == []
        monkeypatch.setattr(
            settings(),
            "scim_bindings",
            {
                ORG_A: SCIMBinding(
                    base_url="https://scim.example.org/v2",
                    token="fixture-backend-token",
                    allow_activation=True,
                )
            },
        )
        adapter = SCIMClient(ORG_A, client)
        adapter.restore("user-123", "employee@example.org")
        adapter.restore("user-123", "employee@example.org")
    assert calls == ["GET", "PATCH", "GET", "GET"]


def prepare(client, db, monkeypatch):
    prepare_offboarding(client, db, monkeypatch)
    monkeypatch.setattr(SCIMClient, "revoke", lambda *args: None)
    consume(db, ORG_A)
    db.commit()
    record = db.scalar(
        select(Employee).where(Employee.organization_id == ORG_A, Employee.user_id == DEV)
    )
    record.verification_status = "approved"
    db.commit()
    monkeypatch.setattr(
        settings(),
        "scim_bindings",
        {
            ORG_A: SCIMBinding(
                base_url="https://scim.example.org/v2",
                token="fixture-backend-token",
                allow_activation=True,
            )
        },
    )
    plan = propose(
        client, record, kind="rehire", role="junior_developer", department="Rehired team"
    )
    approve(client, plan)
    assert client.post(f"/api/v1/hr/lifecycle/{plan}/execute", headers=headers()).status_code == 200
    login(OWNER)
    route = f"/api/v1/hr/lifecycle/{plan}/restore-scim"
    body = {
        "reference": "verified-provider-session-revocation-ticket",
        "provider_sessions_revoked": True,
        "external_access_reviewed": True,
    }
    assert client.post(route, headers=headers(), json=body).status_code == 200
    assert client.post(route, headers=headers(), json=body).status_code == 200
    assert db.scalar(select(Outbox).where(Outbox.topic == "lifecycle.scim.restore")) is not None
    assert db.query(Outbox).filter_by(topic="lifecycle.scim.restore").count() == 1
    return plan


def test_restoration_queue_is_idempotent_but_does_not_automatically_activate_local_access(
    client, db, monkeypatch
):
    plan = prepare(client, db, monkeypatch)
    calls = []

    def restore(self, external, email):
        assert not db.get(Membership, (ORG_A, DEV)).active
        calls.append((external, email))

    monkeypatch.setattr(SCIMClient, "restore", restore)
    consume(db, ORG_A)
    db.commit()
    record = db.get(LifecyclePlan, plan)
    assert record.proposed["integrations"][0]["state"] == "verified_restored"
    assert record.status == "reconciliation_required"
    assert not db.get(Membership, (ORG_A, DEV)).active
    consume(db, ORG_A)
    db.commit()
    assert len(calls) == 1
    response = activate(client, plan)
    assert response.status_code == 200, response.text
    assert response.json()["proposed"]["integrations"][0]["state"] == "verified_restored"
    assert db.get(Membership, (ORG_A, DEV)).active


@pytest.mark.parametrize("change", ["authority", "suspended", "owner_revoked"])
def test_restoration_worker_rechecks_authority_and_suspension(client, db, monkeypatch, change):
    plan = prepare(client, db, monkeypatch)
    if change == "authority":
        monkeypatch.setattr(
            settings(),
            "scim_bindings",
            {
                ORG_A: SCIMBinding(
                    base_url="https://different.example.invalid/v2",
                    token="fixture-backend-token",
                    allow_activation=True,
                )
            },
        )
    elif change == "suspended":
        db.get(Organization, ORG_A).status = "suspended"
    else:
        db.get(Membership, (ORG_A, OWNER)).active = False
    db.commit()
    calls = []
    monkeypatch.setattr(SCIMClient, "restore", lambda *args: calls.append(True))
    consume(db, ORG_A)
    db.commit()
    assert calls == [] and not db.get(Membership, (ORG_A, DEV)).active
    assert db.get(LifecyclePlan, plan).status == "reconciliation_required"


def test_failed_restoration_is_bounded_and_keeps_local_access_revoked(client, db, monkeypatch):
    plan = prepare(client, db, monkeypatch)
    calls = []

    def fail(*args):
        calls.append(True)
        raise HTTPException(503, "Unverified external operation")

    monkeypatch.setattr(SCIMClient, "restore", fail)
    message = db.scalar(select(Outbox).where(Outbox.topic == "lifecycle.scim.restore"))
    for _ in range(5):
        message.available_at = now()
        db.commit()
        consume(db, ORG_A)
        db.commit()
    assert message.status == "dead_letter" and message.attempts == 5 and len(calls) == 5
    assert not db.get(Membership, (ORG_A, DEV)).active
    assert (
        db.get(LifecyclePlan, plan).proposed["integrations"][0]["state"]
        == "failed_manual_review_required"
    )


def test_abandoned_rehire_requires_revocation_attestation_and_never_runs_queued_restore(
    client, db, monkeypatch
):
    plan = prepare(client, db, monkeypatch)
    route = f"/api/v1/hr/lifecycle/{plan}/abort-rehire"
    assert (
        client.post(
            route,
            headers=headers(),
            json={"reference": "external-cleanup-ticket", "external_access_revoked": False},
        ).status_code
        == 422
    )
    result = client.post(
        route,
        headers=headers(),
        json={"reference": "external-cleanup-ticket", "external_access_revoked": True},
    )
    assert result.status_code == 200 and result.json()["status"] == "cancelled"
    calls = []
    monkeypatch.setattr(SCIMClient, "restore", lambda *args: calls.append(True))
    consume(db, ORG_A)
    db.commit()
    assert calls == [] and not db.get(Membership, (ORG_A, DEV)).active
    assert (
        client.post(
            route,
            headers=headers(),
            json={"reference": "external-cleanup-ticket", "external_access_revoked": True},
        ).json()
        == result.json()
    )
