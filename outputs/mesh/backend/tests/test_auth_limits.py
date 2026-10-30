import json

import pytest
from app.auth_limits import account_key
from app.core.config import settings
from pydantic import SecretStr
from redis.exceptions import ConnectionError as RedisConnectionError


def test_private_account_keys_normalize_identity_and_do_not_store_plaintext(monkeypatch):
    monkeypatch.setattr(settings(), "auth_rate_secret", SecretStr("a" * 48))
    monkeypatch.setattr("app.auth_limits.time.time", lambda: 1700000000)
    first = account_key(json.dumps({"email": "Owner@Example.org"}).encode())
    assert first == account_key(json.dumps({"email": " owner@example.org "}).encode())
    assert "owner" not in first and "example.org" not in first
    monkeypatch.setattr(settings(), "auth_rate_secret", SecretStr("b" * 48))
    assert first != account_key(json.dumps({"email": "owner@example.org"}).encode())


def test_account_limit_combines_distributed_auth_attempts_and_retains_security_headers(
    client, monkeypatch
):
    monkeypatch.setattr(settings(), "test_mode", False)
    monkeypatch.setattr(settings(), "auth_rate_secret", SecretStr("a" * 48))
    keys = []

    def evaluate(script, count, key):
        keys.append(key)
        return 21 if key.startswith("mesh:auth:") else 1

    monkeypatch.setattr("app.main.redis_client.eval", evaluate)
    response = client.post(
        "/api/v1/auth/login",
        json={
            "email": "victim@example.org",
            "password": "fixture-password",
            "captcha_token": "captcha",
        },
    )
    assert response.status_code == 429
    assert response.headers["Retry-After"] == "60"
    assert response.headers["Cache-Control"] == "no-store"
    assert response.headers["X-Request-ID"]
    assert len(keys) == 2 and all("victim" not in key for key in keys)


def test_account_limiter_fails_closed_on_redis_error(client, monkeypatch):
    monkeypatch.setattr(settings(), "test_mode", False)
    monkeypatch.setattr(settings(), "auth_rate_secret", SecretStr("a" * 48))

    def evaluate(script, count, key):
        if key.startswith("mesh:auth:"):
            raise RedisConnectionError("Sensitive internal connection detail")
        return 1

    monkeypatch.setattr("app.main.redis_client.eval", evaluate)
    response = client.post(
        "/api/v1/auth/recover", json={"email": "user@example.org", "captcha_token": "captcha"}
    )
    assert response.status_code == 503
    assert "Sensitive" not in response.text
    assert response.headers["X-Content-Type-Options"] == "nosniff"


@pytest.mark.parametrize("body", [b"invalid-json", b"[]", b'{"email":1}'])
def test_malformed_auth_input_cannot_create_identity_keys(body):
    assert account_key(body) is None


def test_body_rejection_is_measured_and_has_security_headers(client):
    from app.core.metrics import render

    response = client.post("/api/v1/auth/login", content=b"x" * 262145)
    assert response.status_code == 413
    assert response.headers["Cache-Control"] == "no-store"
    assert response.headers["X-Request-ID"]
    assert 'method="POST",status="413"' in render()
