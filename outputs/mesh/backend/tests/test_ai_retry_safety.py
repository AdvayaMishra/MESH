import httpx
import pytest
from app.ai import HTTPProvider
from app.core.config import settings
from fastapi import HTTPException


@pytest.mark.parametrize(
    "failure", ["read", "invalid_json", "invalid_schema", "status_429", "status_503"]
)
def test_ambiguous_or_completed_generation_never_silently_repeats(monkeypatch, failure):
    monkeypatch.setattr(settings(), "ai_provider", "gateway")
    monkeypatch.setattr(settings(), "ai_allow_external", True)
    monkeypatch.setattr(settings(), "ai_url", "https://gateway.example.invalid/generate")
    calls = []

    def respond(request):
        calls.append(request)
        if failure == "read":
            raise httpx.ReadTimeout("private endpoint detail")
        if failure.startswith("status_"):
            return httpx.Response(int(failure.split("_")[1]))
        if failure == "invalid_json":
            return httpx.Response(200, content=b"not json")
        return httpx.Response(200, json={"output": {"summary": "missing fields"}})

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        with pytest.raises(HTTPException) as error:
            HTTPProvider(client).generate("owner", {"records": 1})
    assert error.value.status_code == 503 and len(calls) == 1
    assert "private" not in error.value.detail


def test_only_pre_request_connection_failure_can_retry(monkeypatch):
    monkeypatch.setattr(settings(), "ai_provider", "gateway")
    monkeypatch.setattr(settings(), "ai_allow_external", True)
    monkeypatch.setattr(settings(), "ai_url", "https://gateway.example.invalid/generate")
    calls = []

    def respond(request):
        calls.append(request)
        if len(calls) == 1:
            raise httpx.ConnectTimeout("not connected")
        return httpx.Response(
            200,
            json={
                "output": {"summary": "Fixture", "recommendations": [], "limitations": ["Fixture"]},
                "input_tokens": 10,
                "output_tokens": 10,
            },
        )

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        result = HTTPProvider(client).generate("owner", {"records": 1})
    assert result.provider == "gateway" and len(calls) == 2


def test_overall_deadline_does_not_repeat_a_dispatched_generation(monkeypatch):
    monkeypatch.setattr(settings(), "ai_provider", "gateway")
    monkeypatch.setattr(settings(), "ai_allow_external", True)
    monkeypatch.setattr(settings(), "ai_url", "https://gateway.example.invalid/generate")
    clock = [0.0]
    monkeypatch.setattr("app.ai.time.monotonic", lambda: clock[0])
    calls = []

    def respond(request):
        calls.append(request)
        clock[0] = 31.0
        return httpx.Response(
            200,
            json={
                "output": {"summary": "Fixture", "recommendations": [], "limitations": ["Fixture"]}
            },
        )

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        with pytest.raises(HTTPException) as error:
            HTTPProvider(client).generate("owner", {"records": 1})
    assert error.value.status_code == 503 and len(calls) == 1
