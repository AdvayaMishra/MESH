import pytest
from app.auth import Principal
from app.enterprise_schemas import CostInput
from app.finance import record_cost
from app.models import AuditLog, CostRecord, Membership, identifier
from conftest import HR, ORG_A, ORG_B, OWNER, headers, login
from fastapi import HTTPException
from sqlalchemy import func, select, update


def payload(**values):
    return {
        "request_key": identifier(),
        "period": "2026-10",
        "department": "Engineering",
        "category": "cloud",
        "currency": "INR",
        "amount": "10",
        **values,
    }


def test_retry_canonicalizes_money_preserves_one_cost_one_audit_and_same_response(client, db):
    body = payload()
    first = client.post("/api/v1/finance/costs", headers=headers(), json=body)
    assert first.status_code == 201, first.text
    repeated = client.post(
        "/api/v1/finance/costs", headers=headers(), json={**body, "amount": "10.00"}
    )
    assert repeated.status_code == 201 and repeated.json() == first.json()
    assert first.json()["recorded_by"] == OWNER and first.json()["amount"] == "10.00"
    assert db.scalar(select(func.count()).select_from(CostRecord)) == 1
    assert (
        db.scalar(
            select(func.count())
            .select_from(AuditLog)
            .where(AuditLog.action == "finance.cost.recorded")
        )
        == 1
    )
    assert client.get("/api/v1/finance/summary", headers=headers()).json()["total"] == "10.00"


@pytest.mark.parametrize(
    "change",
    [
        {"amount": "11"},
        {"currency": "USD"},
        {"period": "2026-09"},
        {"department": "Finance"},
        {"category": "other"},
    ],
)
def test_changed_body_cannot_reuse_financial_receipt(client, db, change):
    body = payload()
    assert client.post("/api/v1/finance/costs", headers=headers(), json=body).status_code == 201
    assert (
        client.post("/api/v1/finance/costs", headers=headers(), json={**body, **change}).status_code
        == 409
    )
    assert db.scalar(select(func.count()).select_from(CostRecord)) == 1


def test_receipt_is_tenant_and_actor_bound_and_still_requires_write_authority(client, db):
    body = payload()
    original = client.post("/api/v1/finance/costs", headers=headers(), json=body).json()
    foreign = client.post("/api/v1/finance/costs", headers=headers(ORG_B), json=body)
    assert foreign.status_code == 201 and foreign.json()["id"] != original["id"]
    second = identifier()
    db.add(
        Membership(
            organization_id=ORG_A, user_id=second, email="fixture@example.invalid", role="owner"
        )
    )
    db.commit()
    login(second)
    assert client.post("/api/v1/finance/costs", headers=headers(), json=body).status_code == 409
    login(HR)
    assert client.post("/api/v1/finance/costs", headers=headers(), json=body).status_code == 403


def test_request_key_is_required_and_server_audit_fields_cannot_be_forged(client):
    body = payload()
    body.pop("request_key")
    assert client.post("/api/v1/finance/costs", headers=headers(), json=body).status_code == 422
    for extra in (
        {"request_key": "invalid"},
        {"recorded_by": identifier()},
        {"request_digest": "a" * 64},
    ):
        assert (
            client.post(
                "/api/v1/finance/costs", headers=headers(), json={**payload(), **extra}
            ).status_code
            == 422
        )


def test_stale_cached_membership_cannot_authorize_a_financial_write(db):
    member = db.get(Membership, (ORG_A, OWNER))
    assert member.role == "owner"
    db.commit()
    with db.get_bind().begin() as connection:
        connection.execute(
            update(Membership)
            .where(Membership.organization_id == ORG_A, Membership.user_id == OWNER)
            .values(role="junior_developer")
        )
    assert member.role == "owner"  # Deliberately stale identity-map state.
    with pytest.raises(HTTPException) as error:
        record_cost(db, Principal(OWNER, ORG_A, "owner"), CostInput(**payload()))
    assert error.value.status_code == 403
    assert db.scalar(select(func.count()).select_from(CostRecord)) == 0


def test_historical_costs_remain_readable_without_inventing_receipt_provenance(client, db):
    db.add(
        CostRecord(
            organization_id=ORG_A,
            period="2026-10",
            department="Legacy",
            category="other",
            currency="INR",
            amount="5.00",
        )
    )
    db.commit()
    row = client.get("/api/v1/finance/costs", headers=headers()).json()[0]
    assert row["request_key"] is None and row["recorded_by"] is None
    assert client.get("/api/v1/finance/summary", headers=headers()).json()["total"] == "5.00"


def test_finance_aggregates_rows_once_and_refuses_partial_group_totals(client, db, monkeypatch):
    for period, department, amount in [
        ("2026-08", "A", "10.10"),
        ("2026-08", "A", "20.20"),
        ("2026-09", "B", "30.30"),
        ("2026-10", "C", "30.30"),
    ]:
        db.add(
            CostRecord(
                organization_id=ORG_A,
                period=period,
                department=department,
                category="other",
                currency="INR",
                amount=amount,
            )
        )
    db.commit()
    result = client.get("/api/v1/finance/summary", headers=headers()).json()
    assert result["total"] == "90.90" and result["forecast_next_month"] == "30.30"
    assert result["months"]["2026-08"] == "30.30"
    monkeypatch.setattr("app.finance.FINANCE_GROUP_LIMIT", 2)
    assert client.get("/api/v1/finance/summary", headers=headers()).status_code == 503
