import json
from datetime import timedelta
from decimal import Decimal

import httpx
import pytest
from app.ai import HTTPProvider, generate
from app.auth import Principal
from app.core.config import settings
from app.models import AIUsage, now
from conftest import ORG_A, ORG_B, OWNER
from fastapi import HTTPException
from test_ai_admission import Provider, policy


@pytest.mark.parametrize(
    "provider,missing",
    [
        ("gateway", "input_tokens"),
        ("gateway", "output_tokens"),
        ("ollama", "prompt_eval_count"),
        ("ollama", "eval_count"),
    ],
)
def test_missing_provider_usage_is_unknown_not_free_zero(monkeypatch, provider, missing):
    monkeypatch.setattr(settings(), "ai_provider", provider)
    monkeypatch.setattr(settings(), "ai_allow_external", True)
    monkeypatch.setattr(settings(), "ai_url", "https://gateway.example.invalid/generate")
    insight = {"summary": "Synthetic", "recommendations": [], "limitations": ["Fixture"]}
    body = (
        {"output": insight, "input_tokens": 10, "output_tokens": 5}
        if provider == "gateway"
        else {"message": {"content": json.dumps(insight)}, "prompt_eval_count": 10, "eval_count": 5}
    )
    del body[missing]
    calls = []

    def respond(request):
        calls.append(True)
        return httpx.Response(200, json=body)

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        with pytest.raises(HTTPException) as error:
            HTTPProvider(client).generate("owner", {"records": 1})
    assert error.value.status_code == 503 and len(calls) == 1


@pytest.mark.parametrize("currency,cost", [(None, "1"), ("EUR", "1"), ("USD", None)])
def test_aggregate_cost_admission_rejects_incomplete_or_mixed_currency(
    db, monkeypatch, currency, cost
):
    policy(monkeypatch, monthly_cost_limit="100")
    db.add(
        AIUsage(
            organization_id=ORG_A,
            provider="gateway",
            purpose="owner",
            input_units=1,
            output_units=1,
            estimated_cost=Decimal(cost) if cost else None,
            billing_currency=currency,
        )
    )
    adapter = Provider()
    with pytest.raises(HTTPException) as error:
        generate(db, Principal(OWNER, ORG_A, "owner"), "owner", {"records": 1}, adapter)
    assert error.value.status_code == 503 and adapter.calls == 0


def test_monthly_aggregate_ignores_other_tenants_and_prior_periods(db, monkeypatch):
    policy(monkeypatch, monthly_requests=1, monthly_cost_limit="100")
    previous = now().replace(day=1, hour=0, minute=0, second=0, microsecond=0) - timedelta(
        seconds=1
    )
    for organization, when in ((ORG_A, previous), (ORG_B, now())):
        db.add(
            AIUsage(
                organization_id=organization,
                provider="gateway",
                purpose="owner",
                input_units=999999,
                output_units=999999,
                created_at=when,
            )
        )
    adapter = Provider()
    result = generate(db, Principal(OWNER, ORG_A, "owner"), "owner", {"records": 1}, adapter)
    assert adapter.calls == 1 and result["usage"]["estimated_cost"] == Decimal("0.000500")


def test_adapter_cannot_silently_change_the_accounted_provider(db, monkeypatch):
    policy(monkeypatch)

    class WrongProvider(Provider):
        def generate(self, purpose, context):
            result = super().generate(purpose, context)
            result.provider = "unconfigured-provider"
            return result

    with pytest.raises(HTTPException) as error:
        generate(db, Principal(OWNER, ORG_A, "owner"), "owner", {"records": 1}, WrongProvider())
    assert error.value.status_code == 503 and db.query(AIUsage).count() == 0
