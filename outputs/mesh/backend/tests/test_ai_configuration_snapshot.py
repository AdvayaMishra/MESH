"""Operator reloads cannot redirect or reprice an already admitted generation."""

from decimal import Decimal

import httpx
import pytest
from app.ai import HTTPProvider, generate
from app.auth import Principal
from app.core.config import settings
from app.models import AIUsage
from conftest import ORG_A, OWNER
from fastapi import HTTPException
from pydantic import SecretStr
from sqlalchemy import select
from test_ai_admission import Provider, policy


def configured(monkeypatch):
    policy(monkeypatch)
    config = settings()
    monkeypatch.setattr(config, "ai_allow_external", True)
    monkeypatch.setattr(config, "ai_url", "https://first.example.invalid/generate")
    monkeypatch.setattr(config, "ai_api_key", SecretStr("fixture-first-key"))
    return config


def response():
    return httpx.Response(
        200,
        json={
            "output": {"summary": "Fixture", "recommendations": [], "limitations": ["Fixture"]},
            "input_tokens": 10,
            "output_tokens": 5,
        },
    )


def test_http_adapter_freezes_endpoint_model_key_and_provider(monkeypatch):
    config = configured(monkeypatch)
    requests = []

    def respond(request):
        requests.append(request)
        return response()

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        adapter = HTTPProvider(client)
        monkeypatch.setattr(config, "ai_url", "https://second.example.invalid/generate")
        monkeypatch.setattr(config, "ai_model", "second-model")
        monkeypatch.setattr(config, "ai_api_key", SecretStr("fixture-second-key"))
        monkeypatch.setattr(config, "ai_provider", "ollama")
        result = adapter.generate("owner", {"records": 1})
    assert result.provider == "gateway"
    assert len(requests) == 1
    assert requests[0].url.host == "first.example.invalid"
    assert requests[0].headers["Authorization"] == "Bearer fixture-first-key"
    assert b'"model":"operator-test-model"' in requests[0].content


def test_connection_retry_retains_first_endpoint_and_credentials(monkeypatch):
    config = configured(monkeypatch)
    requests = []

    def respond(request):
        requests.append(request)
        if len(requests) == 1:
            monkeypatch.setattr(config, "ai_url", "https://second.example.invalid/generate")
            monkeypatch.setattr(config, "ai_api_key", SecretStr("fixture-second-key"))
            raise httpx.ConnectTimeout("fixture")
        return response()

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        HTTPProvider(client).generate("owner", {"records": 1})
    assert len(requests) == 2
    assert {item.url.host for item in requests} == {"first.example.invalid"}
    assert {item.headers["Authorization"] for item in requests} == {"Bearer fixture-first-key"}


def test_new_adapter_uses_new_configuration(monkeypatch):
    config = configured(monkeypatch)
    first = HTTPProvider()
    monkeypatch.setattr(config, "ai_url", "https://second.example.invalid/generate")
    second = HTTPProvider()
    assert first.config.ai_url != second.config.ai_url


@pytest.mark.parametrize(
    "field,value", [("ai_url", "http://unsafe.invalid"), ("ai_allow_external", False)]
)
def test_invalid_snapshot_cannot_be_enabled_by_later_reload(monkeypatch, field, value):
    config = configured(monkeypatch)
    monkeypatch.setattr(config, field, value)
    requests = []
    with httpx.Client(
        transport=httpx.MockTransport(lambda request: requests.append(request))
    ) as client:
        adapter = HTTPProvider(client)
        monkeypatch.setattr(config, "ai_url", "https://first.example.invalid/generate")
        monkeypatch.setattr(config, "ai_allow_external", True)
        with pytest.raises(HTTPException) as error:
            adapter.generate("owner", {"records": 1})
    assert error.value.status_code == 503 and not requests


def test_admitted_price_and_model_survive_mutation_during_provider_call(db, monkeypatch):
    config = configured(monkeypatch)

    class ReloadingProvider(Provider):
        def generate(self, purpose, context):
            result = super().generate(purpose, context)
            # Mutate the nested policy itself, not just the Settings attribute.
            config.ai_policies[ORG_A].input_price_per_million = Decimal("999")
            config.ai_policies[ORG_A].output_price_per_million = Decimal("999")
            config.ai_policies[ORG_A].currency = "EUR"
            config.ai_model = "changed-model"
            config.ai_provider = "ollama"
            return result

    result = generate(
        db, Principal(OWNER, ORG_A, "owner"), "owner", {"records": 1}, ReloadingProvider()
    )
    assert result["usage"]["estimated_cost"] == Decimal("0.000500")
    assert result["usage"]["currency"] == "USD"
    assert result["usage"]["model"] == "operator-test-model"
    usage = db.scalar(select(AIUsage))
    assert usage.billing_currency == "USD" and usage.model == "operator-test-model"
    assert usage.pricing["input_per_million"] == "2.50"
