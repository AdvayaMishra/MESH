from decimal import Decimal

import pytest
from app.ai_stream import StreamInput
from app.models import CostRecord
from conftest import ORG_A, ORG_B, headers
from pydantic import ValidationError


def cost(db, org, currency, amount):
    db.add(
        CostRecord(
            organization_id=org,
            period="2026-10",
            department="Engineering",
            category="tools",
            currency=currency,
            amount=Decimal(amount),
            source="manual",
        )
    )
    db.commit()


def test_owner_summary_auto_selects_only_recorded_currency(client, db):
    cost(db, ORG_A, "USD", "250")
    cost(db, ORG_B, "INR", "99999")
    response = client.get("/api/v1/ai/owner", headers=headers())
    assert response.status_code == 200
    result = response.json()
    assert result["currency"] == "USD"
    assert "recorded_spending_usd=250" in result["summary"]
    assert "observed_months=1" in result["summary"]
    assert "99999" not in response.text


def test_owner_summary_requires_choice_for_multiple_currencies(client, db):
    cost(db, ORG_A, "USD", "250")
    cost(db, ORG_A, "INR", "1000")
    assert client.get("/api/v1/ai/owner", headers=headers()).status_code == 409
    response = client.get("/api/v1/ai/owner?currency=USD", headers=headers())
    assert response.status_code == 200
    assert "recorded_spending_usd=250" in response.json()["summary"]
    assert "1000" not in response.json()["summary"]
    response = client.get("/api/v1/ai/owner?currency=INR", headers=headers())
    assert "recorded_spending_inr=1000" in response.json()["summary"]


def test_empty_owner_summary_preserves_inr_default_and_zero_observations(client):
    value = client.get("/api/v1/ai/owner", headers=headers()).json()
    assert value["currency"] == "INR"
    assert "observed_months=0" in value["summary"]


@pytest.mark.parametrize("currency", ["usd", "US", "USD,INR", "USD<script>"])
def test_owner_summary_rejects_invalid_currency(client, currency):
    assert (
        client.get("/api/v1/ai/owner", params={"currency": currency}, headers=headers()).status_code
        == 422
    )


def test_stream_currency_is_owner_scoped():
    assert StreamInput(purpose="owner", currency="USD").currency == "USD"
    with pytest.raises(ValidationError):
        StreamInput(purpose="hr", currency="USD")
    with pytest.raises(ValidationError):
        StreamInput(purpose="owner", currency="usd")
