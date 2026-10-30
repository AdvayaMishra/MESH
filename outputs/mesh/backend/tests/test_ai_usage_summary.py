from datetime import UTC, datetime
from decimal import Decimal

import httpx
import pytest
from app.ai import HTTPProvider
from app.core.config import settings
from app.models import AIUsage
from conftest import ANALYST, HR, ORG_A, ORG_B, headers, login
from fastapi import HTTPException


def test_usage_summary_separates_currency_model_and_unknown_costs(client, db):
    when = datetime(2026, 10, 10, tzinfo=UTC)
    for org, currency, cost, model in (
        (ORG_A, "USD", "1.5", "a"),
        (ORG_A, "USD", None, "a"),
        (ORG_A, "EUR", "2", "a"),
        (ORG_A, None, "99", "b"),
        (ORG_B, "USD", "100", "a"),
    ):
        db.add(
            AIUsage(
                organization_id=org,
                provider="gateway",
                purpose="owner",
                model=model,
                input_units=100,
                output_units=10,
                billing_currency=currency,
                estimated_cost=Decimal(cost) if cost else None,
                created_at=when,
            )
        )
    db.add(
        AIUsage(
            organization_id=ORG_A,
            provider="gateway",
            purpose="owner",
            model="excluded",
            input_units=900,
            output_units=900,
            created_at=datetime(2026, 11, 1, tzinfo=UTC),
        )
    )
    db.commit()
    response = client.get("/api/v1/ai/usage/summary?month=2026-10", headers=headers())
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total_groups"] == 3 and body["recorded_successful_only"] is True
    assert (
        body["provider_invoice_reconciled"] is False
        and body["failed_or_ambiguous_dispatches_included"] is False
    )
    usd = next(group for group in body["groups"] if group["currency"] == "USD")
    assert usd["recorded_requests"] == 2 and usd["input_units"] == 200
    assert Decimal(usd["known_estimated_cost"]) == Decimal("1.5") and usd["unpriced_requests"] == 1
    unknown = next(group for group in body["groups"] if group["currency"] is None)
    assert unknown["known_estimated_cost"] is None and unknown["unpriced_requests"] == 1
    empty = client.get("/api/v1/ai/usage/summary?month=2026-10&offset=99", headers=headers()).json()
    assert empty["groups"] == [] and empty["total_groups"] == 3
    assert (
        client.get("/api/v1/ai/usage/summary?month=2026-09", headers=headers()).json()[
            "total_groups"
        ]
        == 0
    )


@pytest.mark.parametrize("month", ["2026-00", "2026-13", "2026-1", "1899-12", "9999-12", "x"])
def test_usage_summary_rejects_invalid_months(client, month):
    assert (
        client.get(
            "/api/v1/ai/usage/summary", params={"month": month}, headers=headers()
        ).status_code
        == 422
    )


@pytest.mark.parametrize("user", [ANALYST, HR])
def test_usage_summary_denies_other_roles(client, user):
    login(user)
    assert client.get("/api/v1/ai/usage/summary", headers=headers()).status_code == 403


def test_model_response_compression_is_rejected_without_regeneration(monkeypatch):
    monkeypatch.setattr(settings(), "ai_provider", "gateway")
    monkeypatch.setattr(settings(), "ai_allow_external", True)
    monkeypatch.setattr(settings(), "ai_url", "https://gateway.example.invalid/generate")
    calls = []

    def respond(request):
        assert request.headers["accept-encoding"] == "identity"
        calls.append(True)
        return httpx.Response(200, headers={"content-encoding": "unsupported"}, content=b"blocked")

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        with pytest.raises(HTTPException) as error:
            HTTPProvider(client).generate("owner", {"records": 1})
    assert error.value.status_code == 503 and len(calls) == 1
