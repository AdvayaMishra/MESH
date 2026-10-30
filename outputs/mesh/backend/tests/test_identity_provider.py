import httpx
import pytest
from app.core.config import settings
from app.identity_provider import Login, SupabaseAuth, provider_tokens
from fastapi import HTTPException


def test_provider_password_authority_and_captcha(monkeypatch):
    monkeypatch.setattr(settings(), "supabase_url", "https://identity.example.org")
    monkeypatch.setattr(settings(), "supabase_anon_key", "public-anon-key")

    def handler(request):
        assert request.url.path == "/auth/v1/token"
        assert b"captcha_token" in request.content
        assert request.headers["apikey"] == "public-anon-key"
        return httpx.Response(
            200,
            json={
                "access_token": "access",
                "refresh_token": "refresh",
                "expires_in": 3600,
                "token_type": "bearer",
            },
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = SupabaseAuth(client).login(
            Login(
                email="owner@example.org", password="secure-test-password", captcha_token="captcha"
            )
        )
    assert result.access_token == "access"


def test_provider_failure_redacts_errors(monkeypatch):
    monkeypatch.setattr(settings(), "supabase_url", "https://identity.example.org")
    monkeypatch.setattr(settings(), "supabase_anon_key", "public-anon-key")
    with httpx.Client(
        transport=httpx.MockTransport(lambda _: httpx.Response(400, json={"secret": "PASSWORD"}))
    ) as client:
        with pytest.raises(HTTPException) as exc:
            SupabaseAuth(client).request("signup", {})
    assert "PASSWORD" not in exc.value.detail


@pytest.mark.parametrize(
    "body",
    [b"[]", b"null", b"not-json", b" " * 131073],
    ids=["array", "null", "invalid_json", "oversized"],
)
def test_provider_malformed_or_oversized_response_is_unavailable(monkeypatch, body):
    monkeypatch.setattr(settings(), "supabase_url", "https://identity.example.org")
    monkeypatch.setattr(settings(), "supabase_anon_key", "public-anon-key")
    with httpx.Client(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, content=body))
    ) as client:
        with pytest.raises(HTTPException) as exc:
            SupabaseAuth(client).request("user", {}, method="GET")
    assert exc.value.status_code == 503


@pytest.mark.parametrize("status,expected", [(302, 503), (429, 429), (503, 503)])
def test_provider_redirect_rate_limit_and_failure(monkeypatch, status, expected):
    monkeypatch.setattr(settings(), "supabase_url", "https://identity.example.org")
    monkeypatch.setattr(settings(), "supabase_anon_key", "public-anon-key")
    calls = []

    def handler(request):
        calls.append(str(request.url))
        return httpx.Response(status, headers={"Location": "https://attacker.invalid"})

    with httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True) as client:
        with pytest.raises(HTTPException) as exc:
            SupabaseAuth(client).request("user", {}, method="GET")
    assert exc.value.status_code == expected
    assert len(calls) == 1


@pytest.mark.parametrize(
    "updates",
    [
        {"access_token": ""},
        {"expires_in": -1},
        {"token_type": "unexpected"},
        {"refresh_token": None},
    ],
)
def test_invalid_provider_session_never_escapes_as_unhandled_error(updates):
    with pytest.raises(HTTPException) as exc:
        provider_tokens(
            {
                "access_token": "access",
                "refresh_token": "refresh",
                "token_type": "bearer",
                "expires_in": 3600,
                **updates,
            }
        )
    assert exc.value.status_code == 503


def test_missing_provider_session_fields_are_unavailable():
    with pytest.raises(HTTPException) as exc:
        provider_tokens({})
    assert exc.value.status_code == 503
