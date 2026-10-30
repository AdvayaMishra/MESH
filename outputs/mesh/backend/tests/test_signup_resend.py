import json

import httpx
import pytest
from app.core.config import settings
from app.identity_provider import ResendSignup, SupabaseAuth
from fastapi import HTTPException
from pydantic import SecretStr
from redis.exceptions import ConnectionError as RedisConnectionError


def test_resend_forwards_only_signup_email_and_captcha(monkeypatch):
    monkeypatch.setattr(settings(), "supabase_url", "https://identity.example.org")
    monkeypatch.setattr(settings(), "supabase_anon_key", "fixture-public-key")
    requests = []

    def handler(request):
        requests.append(request)
        assert request.method == "POST"
        assert str(request.url) == "https://identity.example.org/auth/v1/resend"
        assert json.loads(request.content) == {
            "type": "signup",
            "email": "pending@example.invalid",
            "gotrue_meta_security": {"captcha_token": "private-captcha"},
        }
        assert "authorization" not in request.headers
        return httpx.Response(200, json={})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        assert (
            SupabaseAuth(client).resend_signup(
                ResendSignup(email="pending@example.invalid", captcha_token="private-captcha")
            )
            is None
        )
    assert len(requests) == 1


def test_resend_api_has_generic_acknowledgment_and_no_session(client, monkeypatch):
    received = []
    monkeypatch.setattr(SupabaseAuth, "resend_signup", lambda self, data: received.append(data))
    response = client.post(
        "/api/v1/auth/resend",
        json={"email": "pending@example.invalid", "captcha_token": "private-captcha"},
    )
    assert response.status_code == 202
    assert response.json() == {
        "message": "If signup confirmation is pending, instructions will be sent"
    }
    assert response.headers["Cache-Control"] == "no-store"
    assert len(received) == 1
    assert "private-captcha" not in response.text


@pytest.mark.parametrize(
    "body",
    [
        {"email": "invalid", "captcha_token": "captcha"},
        {"email": "pending@example.invalid"},
        {"email": "pending@example.invalid", "captcha_token": ""},
        {"email": "pending@example.invalid", "captcha_token": "x" * 4097},
        {"email": "pending@example.invalid", "captcha_token": "captcha", "type": "email_change"},
        {
            "email": "pending@example.invalid",
            "captcha_token": "captcha",
            "redirect_to": "https://attacker.invalid",
        },
    ],
)
def test_resend_rejects_invalid_or_expanded_input_before_provider(client, monkeypatch, body):
    def forbidden(*args):
        pytest.fail("Invalid resend input reached the provider")

    monkeypatch.setattr(SupabaseAuth, "resend_signup", forbidden)
    response = client.post("/api/v1/auth/resend", json=body)
    assert response.status_code == 422


@pytest.mark.parametrize("status,expected", [(400, 401), (429, 429), (503, 503), (302, 503)])
def test_resend_provider_failures_are_sanitized_and_never_retried(monkeypatch, status, expected):
    monkeypatch.setattr(settings(), "supabase_url", "https://identity.example.org")
    monkeypatch.setattr(settings(), "supabase_anon_key", "fixture-public-key")
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(
            status,
            json={"error": "private-captcha pending@example.invalid"},
            headers={"Location": "https://attacker.invalid"},
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(HTTPException) as exc:
            SupabaseAuth(client).resend_signup(
                ResendSignup(email="pending@example.invalid", captcha_token="private-captcha")
            )
    assert exc.value.status_code == expected
    assert "private-captcha" not in exc.value.detail
    assert "pending@" not in exc.value.detail
    assert len(requests) == 1


@pytest.mark.parametrize("outcome", ["limit", "unavailable"])
def test_resend_shares_private_account_throttle_and_fails_closed(client, monkeypatch, outcome):
    monkeypatch.setattr(settings(), "test_mode", False)
    monkeypatch.setattr(settings(), "auth_rate_secret", SecretStr("a" * 48))
    keys = []

    def evaluate(script, count, key):
        keys.append(key)
        if key.startswith("mesh:auth:"):
            if outcome == "unavailable":
                raise RedisConnectionError("private-redis-address")
            return 21
        return 1

    monkeypatch.setattr("app.main.redis_client.eval", evaluate)
    monkeypatch.setattr(
        SupabaseAuth, "resend_signup", lambda *args: pytest.fail("Limited request reached provider")
    )
    response = client.post(
        "/api/v1/auth/resend",
        json={"email": "pending@example.invalid", "captcha_token": "captcha"},
    )
    assert response.status_code == (429 if outcome == "limit" else 503)
    assert any(key.startswith("mesh:auth:") for key in keys)
    assert all("pending" not in key for key in keys)
    assert "private-redis-address" not in response.text
