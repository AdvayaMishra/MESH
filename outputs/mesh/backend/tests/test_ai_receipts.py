"""Financial-state contracts; independent commit/rollback is proved on PostgreSQL."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from app import ai_accounting
from app.ai import generate
from app.ai_errors import ProviderNotDispatched
from app.auth import Principal
from app.core.config import AIUsagePolicy, settings
from app.models import AIRequest, AIRequestEvent, AIUsage, now
from conftest import HR, ORG_A, ORG_B, OWNER, headers, login
from fastapi import HTTPException
from sqlalchemy import select
from test_ai_admission import Provider, policy


def actor():
    return Principal(OWNER, ORG_A, "owner")


def current(db):
    return db.scalar(
        select(AIRequest)
        .where(AIRequest.organization_id == ORG_A)
        .order_by(AIRequest.created_at.desc())
    )


def kinds(db, request_id):
    return list(
        db.scalars(
            select(AIRequestEvent.kind)
            .where(AIRequestEvent.request_id == request_id)
            .order_by(AIRequestEvent.position)
        )
    )


def reserve(db, monkeypatch):
    policy(monkeypatch)
    store = ai_accounting.store_for(db, actor())
    record = store.reserve("owner", settings().ai_policies[ORG_A], "a" * 64, "b" * 64)
    return store, record


def test_success_has_one_scoped_receipt_usage_and_private_dispatch_token(client, db, monkeypatch):
    policy(monkeypatch)
    value = generate(db, actor(), "owner", {"records": 7}, Provider())
    record = current(db)
    assert value["usage"]["request_id"] == record.id and record.status == "succeeded"
    usage = db.scalar(select(AIUsage))
    assert usage.request_id == record.id and usage.admission_period_start == record.period_start
    assert kinds(db, record.id) == ["reserved", "dispatched", "succeeded"]
    response = client.get("/api/v1/ai/requests/" + record.id, headers=headers())
    assert response.status_code == 200
    body = response.json()
    assert body["total_events"] == 3
    assert body["request"]["provider_invoice_verified"] is False
    assert body["request"]["amounts_are_provisional"] is True
    assert (
        not {"dispatch_token", "context_digest", "endpoint_digest", "policy_snapshot"}
        & body["request"].keys()
    )


def test_unknown_dispatch_error_is_durable_uncertainty_and_blocks_next_admission(db, monkeypatch):
    policy(monkeypatch, monthly_requests=1)

    class Failed(Provider):
        def generate(self, purpose, context):
            self.calls += 1
            raise RuntimeError("private fixture gateway information")

    provider = Failed()
    with pytest.raises(HTTPException) as error:
        generate(db, actor(), "owner", {"records": 1}, provider)
    assert error.value.status_code == 503 and "private" not in error.value.detail
    record = current(db)
    assert record.status == "ambiguous" and record.reserved_input_units == 4096
    assert record.observed_input_units is None and db.query(AIUsage).count() == 0
    assert kinds(db, record.id) == ["reserved", "dispatched", "ambiguous"]
    with pytest.raises(HTTPException) as error:
        generate(db, actor(), "owner", {"records": 1}, provider)
    assert error.value.status_code == 429 and provider.calls == 1


def test_trusted_pre_send_failure_releases_only_its_attempt(db, monkeypatch):
    policy(monkeypatch, monthly_requests=1)

    class NotSent(Provider):
        def generate(self, purpose, context):
            raise ProviderNotDispatched()

    with pytest.raises(ProviderNotDispatched):
        generate(db, actor(), "owner", {"records": 1}, NotSent())
    first = current(db)
    assert first.status == "not_dispatched"
    generate(db, actor(), "owner", {"records": 1}, Provider())
    assert db.query(AIUsage).count() == 1


def test_usage_above_the_reserved_bound_stays_ambiguous_and_conservatively_admitted(
    db, monkeypatch
):
    policy(monkeypatch, monthly_input_units=8000)

    class OverBound(Provider):
        def generate(self, purpose, context):
            value = super().generate(purpose, context)
            value.input_units = 5000
            return value

    provider = OverBound()
    with pytest.raises(HTTPException) as error:
        generate(db, actor(), "owner", {"records": 1}, provider)
    assert error.value.status_code == 503
    record = current(db)
    assert record.status == "ambiguous" and record.observed_input_units == 5000
    with pytest.raises(HTTPException) as error:
        generate(db, actor(), "owner", {"records": 1}, provider)
    assert error.value.status_code == 429 and provider.calls == 1


def test_receipt_reads_are_owner_only_scoped_bounded_and_preserve_empty_page_total(
    client, db, monkeypatch
):
    policy(monkeypatch)
    value = generate(db, actor(), "owner", {"records": 1}, Provider())
    db.commit()  # SQLite double shares the caller; only PostgreSQL proves independent durability.
    path = "/api/v1/ai/requests/" + value["usage"]["request_id"]
    assert client.get(path, headers=headers(ORG_B)).status_code == 404
    page = client.get("/api/v1/ai/requests?offset=100", headers=headers()).json()
    assert page["requests"] == [] and page["total_requests"] == 1
    assert client.get("/api/v1/ai/requests?limit=0", headers=headers()).status_code == 422
    assert (
        client.get("/api/v1/ai/requests?status=pretend_free", headers=headers()).status_code == 422
    )
    login(HR)
    assert client.get(path, headers=headers()).status_code == 403
    assert client.get("/api/v1/ai/requests", headers=headers()).status_code == 403


def test_expired_pre_dispatch_cancellation_is_repeat_safe_and_fences_dispatch(
    client, db, monkeypatch
):
    store, record = reserve(db, monkeypatch)
    path = f"/api/v1/ai/requests/{record.id}/cancel-expired"
    db.commit()
    assert client.post(path, headers=headers()).status_code == 409
    # SQLite fixture manipulates a deadline; PostgreSQL tests advance the clock
    # because the actual database prohibits changing stored intent/deadlines.
    record = db.get(AIRequest, record.id)
    record.dispatch_deadline = now() - timedelta(seconds=1)
    db.commit()
    assert client.post(path, headers=headers()).status_code == 200
    assert client.post(path, headers=headers()).status_code == 200
    with pytest.raises(HTTPException) as error:
        store.dispatch(record.id, "a" * 36)
    assert error.value.status_code == 409
    assert kinds(db, record.id) == ["reserved", "cancelled"]


def test_owner_charge_reconciliation_waits_for_deadline_and_binds_replay_body(
    client, db, monkeypatch
):
    store, record = reserve(db, monkeypatch)
    store.dispatch(record.id, "a" * 36)
    db.commit()
    path = f"/api/v1/ai/requests/{record.id}/reconcile"
    data = {
        "outcome": "charge",
        "worker_stopped": True,
        "provider_billing_reviewed": True,
        "reference": "fixture-invoice:1",
        "input_units": 100,
        "output_units": 50,
        "amount": "1.250000",
        "currency": "USD",
    }
    assert client.post(path, headers=headers(), json=data).status_code == 409
    record = db.get(AIRequest, record.id)
    record.dispatch_deadline = now() - timedelta(seconds=1)
    db.commit()
    response = client.post(path, headers=headers(), json=data)
    assert response.status_code == 200 and response.json()["status"] == "reconciled_charge"
    assert client.post(path, headers=headers(), json=data).status_code == 200
    assert client.post(path, headers=headers(), json=data | {"amount": "2"}).status_code == 409
    assert kinds(db, record.id).count("reconciled_charge") == 1
    assert db.query(AIUsage).count() == 0
    store.ambiguous(record.id, "a" * 36, (200, 70))
    record = db.get(AIRequest, record.id)
    assert record.status == "ambiguous" and record.observed_cost == Decimal("1.250000")
    assert kinds(db, record.id)[-1] == "late_observation"


def test_wrong_dispatch_token_cannot_release_a_live_attempt(db, monkeypatch):
    store, record = reserve(db, monkeypatch)
    store.dispatch(record.id, "a" * 36)
    store.not_dispatched(record.id, "b" * 36)
    assert db.get(AIRequest, record.id).status == "dispatched"
    assert kinds(db, record.id) == ["reserved", "dispatched"]


def test_gateway_cannot_use_sqlite_without_explicit_accounting_double(db, monkeypatch):
    config = settings()
    monkeypatch.setattr(config, "ai_provider", "gateway")
    monkeypatch.setattr(config, "ai_model", "fixture-model")
    monkeypatch.setattr(
        config, "ai_policies", {ORG_A: AIUsagePolicy(provider="gateway", model="fixture-model")}
    )
    provider = Provider()
    with pytest.raises(HTTPException) as error:
        generate(db, actor(), "owner", {"records": 1}, provider)
    assert error.value.status_code == 503 and provider.calls == 0
    assert db.query(AIRequest).count() == 0


def test_crossing_utc_month_before_dispatch_cancels_without_sending(db, monkeypatch):
    store, _ = reserve(db, monkeypatch)
    store.clock = lambda: datetime(2026, 6, 30, 23, 59, 50, tzinfo=UTC)
    request = store.reserve("owner", settings().ai_policies[ORG_A], "a" * 64, "b" * 64)
    store.clock = lambda: datetime(2026, 7, 1, tzinfo=UTC)
    with pytest.raises(HTTPException) as error:
        store.dispatch(request.id, "a" * 36)
    assert error.value.status_code == 409
    assert db.get(AIRequest, request.id).status == "cancelled"
    assert kinds(db, request.id) == ["reserved", "cancelled"]
