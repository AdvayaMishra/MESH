import json

import httpx
import pytest
from app.core.config import SCIMBinding, settings
from app.lifecycle_integrations import SCIMClient
from app.models import (
    Employee,
    IntegrationAccount,
    LifecyclePlan,
    Membership,
    Organization,
    Outbox,
    identifier,
)
from app.worker import consume
from conftest import DEV, HR, ORG_A, ORG_B, OWNER, headers, login
from fastapi import HTTPException
from sqlalchemy import select


def configure(monkeypatch):
    monkeypatch.setattr(
        settings(),
        "scim_bindings",
        {
            ORG_A: SCIMBinding(
                base_url="https://scim.example.org/v2", token="fixture-backend-token"
            ),
        },
    )


def test_scim_deactivation_verifies_identity_and_result_without_restoring(monkeypatch):
    configure(monkeypatch)
    active = True
    methods = []

    def handler(request):
        nonlocal active
        methods.append(request.method)
        assert request.url.path == "/v2/Users/user-123"
        assert request.headers["Authorization"] == "Bearer fixture-backend-token"
        if request.method == "PATCH":
            assert json.loads(request.content)["Operations"] == [
                {"op": "replace", "path": "active", "value": False}
            ]
            active = False
            return httpx.Response(204)
        return httpx.Response(
            200,
            json={"id": "user-123", "userName": "employee@example.org", "active": active},
            headers={"ETag": 'W/"fixture-v1"'},
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        adapter = SCIMClient(ORG_A, client)
        adapter.revoke("user-123", "employee@example.org")
        adapter.revoke("user-123", "employee@example.org")
    assert methods == ["GET", "PATCH", "GET", "GET"]


def test_scim_mismatched_external_identity_never_mutates_the_account(monkeypatch):
    configure(monkeypatch)
    methods = []

    def handler(request):
        methods.append(request.method)
        return httpx.Response(
            200, json={"id": "user-123", "userName": "other@example.org", "active": True}
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(HTTPException) as exc:
            SCIMClient(ORG_A, client).revoke("user-123", "employee@example.org")
    assert exc.value.status_code == 409 and methods == ["GET"]


def prepare_offboarding(client, db, monkeypatch):
    configure(monkeypatch)
    employee = Employee(
        id=identifier(),
        organization_id=ORG_A,
        user_id=DEV,
        name="Fixture employee",
        department="Engineering",
        status="active",
    )
    db.add(employee)
    db.add(
        IntegrationAccount(
            organization_id=ORG_A, user_id=DEV, provider="scim", external_id="user-123"
        )
    )
    db.commit()
    login(HR)
    response = client.post(
        "/api/v1/hr/lifecycle",
        headers=headers(),
        json={"employee_id": employee.id, "kind": "offboarding"},
    )
    assert response.status_code == 201, response.text
    plan = response.json()["id"]
    login(OWNER)
    assert (
        client.post(
            f"/api/v1/hr/lifecycle/{plan}/decision",
            headers=headers(),
            json={"decision": "approved"},
        ).status_code
        == 200
    )
    login(HR)
    response = client.post(f"/api/v1/hr/lifecycle/{plan}/execute", headers=headers())
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "reconciliation_required"
    assert db.get(Membership, (ORG_A, DEV)).active is False
    return plan


def test_offboarding_queue_verifies_scim_after_local_revocation_even_when_org_suspended(
    client, db, monkeypatch
):
    plan = prepare_offboarding(client, db, monkeypatch)
    calls = []

    def revoke(self, external, email):
        assert not db.get(Membership, (ORG_A, DEV)).active
        calls.append((external, email))

    monkeypatch.setattr(SCIMClient, "revoke", revoke)
    db.get(Organization, ORG_A).status = "suspended"
    db.commit()
    consume(db, ORG_A)
    db.commit()
    assert len(calls) == 1
    record = db.get(LifecyclePlan, plan)
    assert record.status == "completed"
    assert record.proposed["integrations"][0]["state"] == "verified_revoked"
    assert consume(db, ORG_A) >= 0
    assert len(calls) == 1


def test_external_failure_retains_local_revocation_and_exposes_retry_state(client, db, monkeypatch):
    plan = prepare_offboarding(client, db, monkeypatch)

    def unavailable(*args):
        raise HTTPException(503, "Provider unavailable")

    monkeypatch.setattr(SCIMClient, "revoke", unavailable)
    consume(db, ORG_A)
    db.commit()
    record = db.get(LifecyclePlan, plan)
    assert record.status == "reconciliation_required"
    assert record.proposed["integrations"][0]["state"] == "retrying"
    assert not db.get(Membership, (ORG_A, DEV)).active
    message = db.scalar(select(Outbox).where(Outbox.topic == "lifecycle.scim.revoke"))
    assert message.status == "pending" and message.attempts == 1


def test_scim_binding_is_tenant_bound_and_requires_employee_identity_verification(
    client, db, monkeypatch
):
    configure(monkeypatch)
    employee = Employee(
        id=identifier(),
        organization_id=ORG_A,
        user_id=DEV,
        name="Fixture employee",
        department="Engineering",
        status="active",
    )
    db.add(employee)
    db.commit()
    calls = []
    monkeypatch.setattr(
        SCIMClient, "user", lambda self, external, email: calls.append((external, email))
    )
    login(HR)
    endpoint = f"/api/v1/hr/employees/{employee.id}/scim-account"
    response = client.post(endpoint, headers=headers(), json={"external_id": "user-123"})
    assert response.status_code == 201, response.text
    assert calls == [("user-123", DEV + "@example.org")]
    assert (
        client.post(endpoint, headers=headers(ORG_B), json={"external_id": "user-123"}).status_code
        == 404
    )
    assert (
        client.post(endpoint, headers=headers(), json={"external_id": "../other"}).status_code
        == 422
    )


def test_scim_cannot_use_another_tenants_configuration(monkeypatch):
    configure(monkeypatch)
    with pytest.raises(HTTPException) as exc:
        SCIMClient(ORG_B)
    assert exc.value.status_code == 503
