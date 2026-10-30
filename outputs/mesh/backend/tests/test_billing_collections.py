from datetime import timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from app.auth import Principal
from app.aws_billing import AWSBillingReport, CurrencyCost, ServiceCost, period_bounds
from app.billing_collections import cancel_collection, current_authority, request_collection
from app.billing_worker import run_once
from app.core.config import settings
from app.models import BillingCollection, IdentitySession, Membership, Organization, now
from conftest import ANALYST, HR, ORG_A, ORG_B, OWNER, headers, login
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

BASE = "/api/v1/finance/cloud-billing/aws/collections"
ROLE = "arn:aws:iam::012345678901:role/mesh-billing"
P = Principal(OWNER, ORG_A, "owner")


@pytest.fixture(autouse=True)
def binding(monkeypatch):
    monkeypatch.setattr(settings(), "aws_billing_role_bindings", {ORG_A: ROLE, ORG_B: ROLE})


def report(organization, period, **changes):
    _, start, end = period_bounds(period, now().date())
    data = dict(
        organization_id=organization,
        provider_account_id="012345678901",
        period=period,
        period_start=start,
        period_end=end,
        estimated=True,
        collected_at=now(),
        observations=[ServiceCost(service="Amazon S3", amount=Decimal("-1.25001"), currency="USD")],
        totals=[CurrencyCost(amount=Decimal("-1.25001"), currency="USD")],
        limitations=["Synthetic SDK test fixture; no AWS calls"],
    )
    data.update(changes)
    return AWSBillingReport(**data)


def admit(db, p=P):
    row = request_collection(db, p, request_key=uuid4(), period=now().strftime("%Y-%m"))
    db.commit()
    return row


def factory(db, monkeypatch):
    result = sessionmaker(db.get_bind(), expire_on_commit=False)
    monkeypatch.setattr("app.billing_worker.SessionFactory", result)
    return result


def test_admission_replay_and_actor_period_binding(client, db):
    login(OWNER)
    payload = {"request_key": str(uuid4()), "period": now().strftime("%Y-%m")}
    first = client.post(BASE, headers=headers(), json=payload)
    assert first.status_code == 202, first.text
    replay = client.post(BASE, headers=headers(), json=payload)
    assert replay.json()["id"] == first.json()["id"]
    assert db.scalars(select(BillingCollection)).all().__len__() == 1
    changed = {**payload, "period": (now().replace(day=1) - timedelta(days=1)).strftime("%Y-%m")}
    assert client.post(BASE, headers=headers(), json=changed).status_code == 409
    assert client.get(BASE + "/" + first.json()["id"], headers=headers(ORG_B)).status_code == 404
    assert (
        client.get(BASE + "/" + first.json()["id"] + "/report", headers=headers()).status_code
        == 409
    )
    listing = client.get(BASE + "?offset=99", headers=headers()).json()
    assert listing["items"] == [] and listing["total"] == 1


@pytest.mark.parametrize("actor", [ANALYST, HR])
def test_non_finance_roles_cannot_admit_or_read(client, actor):
    login(actor)
    assert client.get(BASE, headers=headers()).status_code == 403
    assert (
        client.post(
            BASE,
            headers=headers(),
            json={"request_key": str(uuid4()), "period": now().strftime("%Y-%m")},
        ).status_code
        == 403
    )


def test_worker_commits_dispatch_before_provider_and_retains_exact_report(client, db, monkeypatch):
    row = admit(db)
    sessions = factory(db, monkeypatch)
    calls = []

    def runner(org, period):
        with sessions() as other:
            observed = other.get(BillingCollection, row.id)
            assert (
                observed.status == "running" and observed.dispatch_token and observed.attempts == 1
            )
        calls.append(True)
        return report(org, period)

    assert run_once(ORG_A, runner)
    db.expire_all()
    saved = db.get(BillingCollection, row.id)
    assert saved.status == "completed" and saved.report["totals"][0]["amount"] == "-1.25001"
    assert not run_once(ORG_A, runner) and len(calls) == 1
    login(OWNER)
    response = client.get(BASE + "/" + row.id + "/report", headers=headers())
    assert response.status_code == 200, response.text
    assert response.json()["totals"][0]["amount"] == "-1.25001"
    assert response.json()["invoice_verified"] is False
    assert "report" not in client.get(BASE, headers=headers()).json()["items"][0]


@pytest.mark.parametrize("mutation", ["revoke", "role", "suspend", "binding", "cancel", "session"])
def test_post_provider_authority_change_discards_result(db, monkeypatch, mutation):
    principal = P
    if mutation == "session":
        session_id = str(uuid4())
        db.add(
            IdentitySession(
                user_id=OWNER,
                provider_session_id=session_id,
                client_hint="Fixture",
                ip_digest="0" * 64,
                expires_at=now() + timedelta(hours=1),
            )
        )
        db.commit()
        principal = Principal(
            OWNER, ORG_A, "owner", session_id, "aal2", now() + timedelta(hours=1), now()
        )
    row = admit(db, principal)
    sessions = factory(db, monkeypatch)

    def runner(org, period):
        with sessions.begin() as other:
            if mutation == "revoke":
                other.get(Membership, (ORG_A, OWNER)).active = False
            elif mutation == "role":
                other.get(Membership, (ORG_A, OWNER)).role = "hr"
            elif mutation == "suspend":
                other.get(Organization, ORG_A).status = "suspended"
            elif mutation == "cancel":
                cancel_collection(other, P, UUID(row.id))
            elif mutation == "session":
                other.scalar(
                    select(IdentitySession).where(
                        IdentitySession.provider_session_id == principal.session_id
                    )
                ).revoked_at = now()
        if mutation == "binding":
            monkeypatch.setattr(settings(), "aws_billing_role_bindings", {})
        return report(org, period)

    assert run_once(ORG_A, runner)
    db.expire_all()
    current = db.get(BillingCollection, row.id)
    assert current.status == "cancelled" and current.report is None


def test_expired_dispatched_job_is_ambiguous_without_another_provider_call(db, monkeypatch):
    row = admit(db)
    row.status, row.attempts, row.dispatch_token = "running", 1, str(uuid4())
    row.dispatched_at = now() - timedelta(minutes=10)
    row.lease_until = now() - timedelta(minutes=1)
    db.commit()
    factory(db, monkeypatch)
    assert run_once(ORG_A, lambda *args: pytest.fail("Ambiguous paid read was repeated"))
    db.expire_all()
    current = db.get(BillingCollection, row.id)
    assert current.status == "ambiguous" and current.error_code == "dispatch_outcome_unknown"


def test_provider_failure_never_automatically_retries(db, monkeypatch):
    row = admit(db)
    factory(db, monkeypatch)

    def fail(*args):
        raise RuntimeError("DO_NOT_EXPOSE")

    assert run_once(ORG_A, fail)
    db.expire_all()
    current = db.get(BillingCollection, row.id)
    assert (
        current.status == "failed"
        and current.attempts == 1
        and current.error_code == "provider_unavailable_or_invalid"
    )
    assert not run_once(ORG_A, lambda *args: pytest.fail("Failed paid read was repeated"))


@pytest.mark.parametrize("wrong", ["tenant", "account", "period", "future", "synthetic"])
def test_scope_or_time_mismatch_is_not_published(db, monkeypatch, wrong):
    row = admit(db)
    factory(db, monkeypatch)

    def runner(org, period):
        if wrong == "tenant":
            return report(ORG_B, period)
        if wrong == "account":
            return report(org, period, provider_account_id="999999999999")
        if wrong == "future":
            return report(org, period, collected_at=now() + timedelta(days=1))
        if wrong == "synthetic":
            return report(org, period, synthetic=True, provenance="synthetic_fixture")
        previous = (now().replace(day=1) - timedelta(days=1)).strftime("%Y-%m")
        return report(org, previous)

    assert run_once(ORG_A, runner)
    db.expire_all()
    assert db.get(BillingCollection, row.id).status == "failed"
    assert db.get(BillingCollection, row.id).report is None


def test_pending_limit_and_missing_binding_are_admission_failures(db, monkeypatch):
    for _ in range(3):
        admit(db)
    with pytest.raises(HTTPException) as error:
        admit(db)
    assert error.value.status_code == 429
    db.rollback()
    monkeypatch.setattr(settings(), "aws_billing_role_bindings", {})
    with pytest.raises(HTTPException) as error:
        request_collection(db, P, request_key=uuid4(), period=now().strftime("%Y-%m"))
    assert error.value.status_code == 503


def test_report_totals_are_validated_before_storage():
    period = now().strftime("%Y-%m")
    with pytest.raises(ValueError):
        report(ORG_A, period, totals=[CurrencyCost(currency="USD", amount=1)])
    with pytest.raises(ValueError):
        report(ORG_A, period, synthetic=True)


def test_synthetic_rows_are_not_exposed_by_normal_finance_routes(client, db):
    row = admit(db)
    row.synthetic = True
    db.commit()
    login(OWNER)
    assert client.get(BASE + "/" + row.id, headers=headers()).status_code == 404
    assert client.get(BASE, headers=headers()).json()["total"] == 0


def test_api_rejects_client_supplied_report_or_account(client):
    login(OWNER)
    response = client.post(
        BASE,
        headers=headers(),
        json={
            "request_key": str(uuid4()),
            "period": now().strftime("%Y-%m"),
            "provider_account_id": "999999999999",
            "report": {},
        },
    )
    assert response.status_code == 422


def test_current_finance_authority_rechecks_session_and_role(db):
    db.get(Membership, (ORG_A, OWNER)).active = False
    db.flush()
    with pytest.raises(HTTPException) as error:
        current_authority(db, P)
    assert error.value.status_code == 403


def test_daily_limit_preserves_replay_without_another_admission(db):
    first = None
    for _ in range(20):
        row = admit(db)
        first = first or row
        cancel_collection(db, P, UUID(row.id))
        db.commit()
    replay = request_collection(db, P, request_key=UUID(first.request_key), period=first.period)
    assert replay.id == first.id
    with pytest.raises(HTTPException) as error:
        request_collection(db, P, request_key=uuid4(), period=first.period)
    assert error.value.status_code == 429


@pytest.mark.parametrize("change", ["revoke", "binding"])
def test_revoked_queued_job_never_contacts_provider(db, monkeypatch, change):
    row = admit(db)
    if change == "revoke":
        db.get(Membership, (ORG_A, OWNER)).active = False
        db.commit()
    else:
        monkeypatch.setattr(settings(), "aws_billing_role_bindings", {})
    factory(db, monkeypatch)
    assert run_once(ORG_A, lambda *args: pytest.fail("Revoked admission contacted provider"))
    db.expire_all()
    current = db.get(BillingCollection, row.id)
    assert current.status == "cancelled" and current.attempts == 0 and current.dispatched_at is None


def test_cross_owner_request_key_cannot_be_reused(db):
    row = admit(db)
    user = str(uuid4())
    db.add(
        Membership(
            organization_id=ORG_A, user_id=user, email=user + "@example.invalid", role="owner"
        )
    )
    db.commit()
    with pytest.raises(HTTPException) as error:
        request_collection(
            db,
            Principal(user, ORG_A, "owner"),
            request_key=UUID(row.request_key),
            period=row.period,
        )
    assert error.value.status_code == 409


def test_mfa_and_missing_runtime_session_fail_closed(db, monkeypatch):
    monkeypatch.setattr(settings(), "require_privileged_mfa", True)
    with pytest.raises(HTTPException) as error:
        current_authority(db, P)
    assert error.value.status_code == 403
    monkeypatch.setattr(settings(), "require_privileged_mfa", False)
    monkeypatch.setattr(settings(), "test_mode", False)
    with pytest.raises(HTTPException) as error:
        current_authority(db, P)
    assert error.value.status_code == 401


def test_result_arriving_after_lease_expiry_is_ambiguous(db, monkeypatch):
    row = admit(db)
    factory(db, monkeypatch)
    original_now = now

    def runner(org, period):
        result = report(org, period)
        monkeypatch.setattr("app.billing_worker.now", lambda: original_now() + timedelta(minutes=6))
        return result

    assert run_once(ORG_A, runner)
    db.expire_all()
    current = db.get(BillingCollection, row.id)
    assert current.status == "ambiguous" and current.report is None


def test_synthetic_queue_neither_consumes_production_quota_nor_calls_provider(db, monkeypatch):
    for _ in range(3):
        db.add(
            BillingCollection(
                organization_id=ORG_A,
                requested_by=OWNER,
                requested_aal="aal1",
                request_key=str(uuid4()),
                period=now().strftime("%Y-%m"),
                provider_account_id="012345678901",
                binding_revision="0" * 64,
                synthetic=True,
            )
        )
    db.commit()
    row = admit(db)
    factory(db, monkeypatch)
    calls = []

    def runner(org, period):
        calls.append(True)
        return report(org, period)

    assert run_once(ORG_A, runner) and not run_once(ORG_A, runner)
    assert len(calls) == 1
    db.expire_all()
    assert db.get(BillingCollection, row.id).status == "completed"
    assert (
        len(
            db.scalars(
                select(BillingCollection).where(
                    BillingCollection.synthetic.is_(True), BillingCollection.status == "queued"
                )
            ).all()
        )
        == 3
    )


def test_mutated_provider_dto_is_revalidated_before_publication(db, monkeypatch):
    row = admit(db)
    factory(db, monkeypatch)

    def runner(org, period):
        result = report(org, period)
        result.totals = [CurrencyCost(currency="USD", amount=Decimal("999"))]
        return result

    assert run_once(ORG_A, runner)
    db.expire_all()
    saved = db.get(BillingCollection, row.id)
    assert saved.status == "failed" and saved.report is None
