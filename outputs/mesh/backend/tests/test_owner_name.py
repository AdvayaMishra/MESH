import json
from datetime import timedelta
from types import SimpleNamespace

import httpx
import jwt
import pytest
from app.auth import Identity, identity
from app.core.config import settings
from app.identity_provider import Login, Signup, SupabaseAuth, owner_name_from_profile
from app.main import app
from app.models import Employee, identifier, now
from conftest import HR, OWNER, headers
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import ValidationError

BASE = {
    "email": "owner@example.org",
    "password": "secure-test-password",
    "captcha_token": "captcha",
}


@pytest.mark.parametrize("name", ["  Ada Lovelace  ", "Advaya Mishra", "नंदिनी शर्मा", "محمد علي"])
def test_signup_normalizes_and_preserves_unicode_owner_names(name):
    assert Signup(**BASE, owner_name=name).owner_name == name.strip()


@pytest.mark.parametrize(
    "name", ["", " ", "\n", "A\nB", "A\x00B", "A\u202eB", "A" * 201, {"role": "owner"}]
)
def test_invalid_owner_names_are_rejected(name):
    with pytest.raises(ValidationError):
        Signup(**BASE, owner_name=name)


def test_signup_sends_only_display_metadata_to_single_password_authority(monkeypatch):
    monkeypatch.setattr(settings(), "supabase_url", "https://identity.example.org")
    monkeypatch.setattr(settings(), "supabase_anon_key", "public-key")
    calls = []

    def handler(request):
        payload = json.loads(request.content)
        assert request.url.path == "/auth/v1/signup"
        assert payload["data"] == {"owner_name": "Ada Lovelace"}
        assert payload["password"] == BASE["password"]
        assert payload["gotrue_meta_security"] == {"captcha_token": "captcha"}
        assert "role" not in payload and "app_metadata" not in payload
        calls.append(payload)
        return httpx.Response(200, json={})

    with httpx.Client(transport=httpx.MockTransport(handler)) as provider:
        SupabaseAuth(provider).signup(Signup(**BASE, owner_name=" Ada Lovelace "))
    assert len(calls) == 1


def test_legacy_signup_omits_metadata_and_login_rejects_registration_fields(monkeypatch):
    captured = []
    monkeypatch.setattr(
        SupabaseAuth, "request", lambda self, path, payload: captured.append(payload)
    )
    SupabaseAuth().signup(Signup(**BASE))
    assert "data" not in captured[0]
    with pytest.raises(ValidationError):
        Login(**BASE, owner_name="Not a login parameter")
    with pytest.raises(ValidationError):
        Signup(**BASE, owner_name="Ada", role="owner")


@pytest.mark.parametrize(
    "metadata",
    [
        None,
        [],
        "owner",
        {},
        {"owner_name": 7},
        {"owner_name": []},
        {"owner_name": ""},
        {"owner_name": "A\nB"},
        {"owner_name": "A" * 201},
    ],
)
def test_malformed_or_legacy_metadata_has_no_display_name(metadata):
    assert owner_name_from_profile({"user_metadata": metadata}) is None


def test_identity_uses_current_confirmed_provider_profile_not_jwt_metadata(monkeypatch):
    key = ec.generate_private_key(ec.SECP256R1())
    uid, sid = identifier(), identifier()
    monkeypatch.setattr(settings(), "supabase_url", "https://identity.example.org")
    monkeypatch.setattr(
        "app.auth._jwks",
        SimpleNamespace(get_signing_key_from_jwt=lambda _: SimpleNamespace(key=key.public_key())),
    )
    token = jwt.encode(
        {
            "sub": uid,
            "session_id": sid,
            "email": "owner@example.org",
            "iss": "https://identity.example.org/auth/v1",
            "aud": "authenticated",
            "iat": now(),
            "exp": now() + timedelta(minutes=5),
            "user_metadata": {"owner_name": "Stale token name", "role": "owner"},
        },
        key,
        algorithm="ES256",
    )
    monkeypatch.setattr(
        SupabaseAuth,
        "request",
        lambda *a, **kw: {
            "id": uid,
            "email": "owner@example.org",
            "email_confirmed_at": now().isoformat(),
            "user_metadata": {"owner_name": " Current provider name ", "role": "owner"},
        },
    )
    who = identity(HTTPAuthorizationCredentials(scheme="Bearer", credentials=token))
    assert who.owner_name == "Current provider name" and who.user_id == uid
    assert not hasattr(who, "role")


def test_profile_returns_owner_name_and_prefers_employee_display_record(client, db):
    app.dependency_overrides[identity] = lambda: Identity(
        OWNER, OWNER + "@example.org", owner_name="Owner Name"
    )
    response = client.get("/api/v1/users/me", headers=headers())
    assert response.status_code == 200
    assert response.json()["owner_name"] == response.json()["name"] == "Owner Name"
    db.add(
        Employee(
            organization_id=headers()["X-Organization-ID"],
            user_id=OWNER,
            name="Employee display",
            department="Management",
        )
    )
    db.commit()
    value = client.get("/api/v1/users/me", headers=headers()).json()
    assert value["name"] == "Employee display" and value["owner_name"] == "Owner Name"


def test_profile_display_metadata_cannot_grant_owner_authority(client):
    app.dependency_overrides[identity] = lambda: Identity(
        HR, HR + "@example.org", owner_name="Owner"
    )
    value = client.get("/api/v1/users/me", headers=headers()).json()
    assert value["role"] == "hr" and value["owner_name"] is None
    assert client.get("/api/v1/finance/costs", headers=headers()).status_code == 403
