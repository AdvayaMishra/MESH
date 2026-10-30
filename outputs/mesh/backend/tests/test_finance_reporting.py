from decimal import Decimal

import pytest
from app.billing import BillingObservation, FixtureBillingAdapter, live_billing_adapter
from conftest import ORG_B, headers
from fastapi import HTTPException
from pydantic import ValidationError
from test_finance_idempotency import payload


def test_budget_replay_variance_and_missing_budget_are_explicit(client):
    body = {"period": "2026-10", "currency": "INR", "amount": "20"}
    first = client.post("/api/v1/finance/budgets", headers=headers(), json=body)
    assert first.status_code == 201, first.text
    assert (
        client.post(
            "/api/v1/finance/budgets", headers=headers(), json={**body, "amount": "20.00"}
        ).json()
        == first.json()
    )
    assert (
        client.post(
            "/api/v1/finance/budgets", headers=headers(), json={**body, "amount": "21"}
        ).status_code
        == 409
    )
    for values in ({"amount": "5"}, {"period": "2026-11", "amount": "9"}):
        assert (
            client.post(
                "/api/v1/finance/costs", headers=headers(), json=payload(**values)
            ).status_code
            == 201
        )
    rows = client.get("/api/v1/finance/budget-variance", headers=headers()).json()
    assert rows[0]["variance"] == "-15.00" and rows[0]["variance_percent"] == "-75.00"
    assert rows[0]["over_budget"] is False
    assert rows[1]["budget"] is None and rows[1]["over_budget"] is None
    assert client.get("/api/v1/finance/budget-variance", headers=headers(ORG_B)).json() == []
    assert client.get("/api/v1/finance/budgets?period=2026-11", headers=headers()).json() == []
    assert (
        client.get(
            f"/api/v1/finance/budgets/{first.json()['id']}/variance", headers=headers()
        ).json()["remaining"]
        == "15.00"
    )


def test_zero_budget_does_not_divide_by_zero(client):
    assert (
        client.post(
            "/api/v1/finance/budgets",
            headers=headers(),
            json={"period": "2026-10", "currency": "INR", "amount": "0"},
        ).status_code
        == 201
    )
    row = client.get("/api/v1/finance/budget-variance", headers=headers()).json()[0]
    assert row["variance_percent"] is None and row["over_budget"] is False


def test_usage_aggregates_only_matching_currency_provider_and_unit(client):
    for values in (
        {"usage_quantity": "2", "usage_unit": "hours", "billing_provider": "aws"},
        {"usage_quantity": "3", "usage_unit": "hours", "billing_provider": "aws"},
        {"usage_quantity": "4", "usage_unit": "requests", "billing_provider": "aws"},
        {
            "usage_quantity": "8",
            "usage_unit": "hours",
            "billing_provider": "gcp",
            "currency": "USD",
        },
    ):
        response = client.post("/api/v1/finance/costs", headers=headers(), json=payload(**values))
        assert response.status_code == 201, response.text
    rows = client.get("/api/v1/finance/usage?billing_provider=aws", headers=headers()).json()
    assert len(rows) == 2
    assert Decimal(rows[0]["quantity"]) == 5 and Decimal(rows[0]["recorded_cost"]) == 20
    assert rows[0]["provenance"] == "reported_records_only"
    assert client.get("/api/v1/finance/usage", headers=headers(ORG_B)).json() == []
    assert client.get("/api/v1/finance/usage?period=2026-13", headers=headers()).status_code == 422


@pytest.mark.parametrize(
    "values",
    [
        {"usage_quantity": "2"},
        {"usage_unit": "hours"},
        {"usage_quantity": "-1", "usage_unit": "hours"},
        {"usage_quantity": "2", "usage_unit": "hours", "category": "other"},
    ],
)
def test_invalid_usage_is_rejected(client, values):
    assert (
        client.post("/api/v1/finance/costs", headers=headers(), json=payload(**values)).status_code
        == 422
    )


def test_billing_fixture_is_explicit_bounded_and_does_not_enable_live_billing():
    row = BillingObservation(
        source_reference="synthetic-hour",
        period="2026-10",
        department="Engineering",
        currency="INR",
        amount="10",
        usage_quantity="2",
        usage_unit="hours",
    )
    adapter = FixtureBillingAdapter("aws", [row])
    result = adapter.collect("2026-10")
    assert result.provenance == "fixture" and len(result.observations) == 1
    result.observations[0].department = "Changed"
    assert adapter.collect("2026-10").observations[0].department == "Engineering"
    assert adapter.collect("2026-11").observations == []
    with pytest.raises(ValueError):
        FixtureBillingAdapter("aws", [row, row])
    with pytest.raises(ValidationError):
        adapter.collect("2026-13")
    with pytest.raises(HTTPException) as error:
        live_billing_adapter("aws")
    assert error.value.status_code == 503
