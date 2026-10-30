from datetime import timedelta
from types import SimpleNamespace

import jwt
import pytest
from app.auth import identity
from app.core.config import settings
from app.models import identifier, now
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from jwt.exceptions import PyJWKClientConnectionError


@pytest.mark.parametrize("invalid", ["signature", "audience", "issuer", "expired", "missing_exp"])
def test_invalid_jwt_rejected(monkeypatch, invalid):
    key = ec.generate_private_key(ec.SECP256R1())
    other = ec.generate_private_key(ec.SECP256R1())
    monkeypatch.setattr(settings(), "supabase_url", "https://identity.example.org")
    monkeypatch.setattr(
        "app.auth._jwks",
        SimpleNamespace(get_signing_key_from_jwt=lambda _: SimpleNamespace(key=key.public_key())),
    )
    claims = {
        "sub": identifier(),
        "session_id": identifier(),
        "email": "verified@example.org",
        "iss": "https://identity.example.org/auth/v1",
        "aud": "authenticated",
        "iat": now(),
        "exp": now() + timedelta(minutes=5),
    }
    if invalid == "audience":
        claims["aud"] = "wrong"
    elif invalid == "issuer":
        claims["iss"] = "https://attacker.example.org/auth/v1"
    elif invalid == "expired":
        claims["exp"] = now() - timedelta(seconds=1)
    elif invalid == "missing_exp":
        del claims["exp"]
    token = jwt.encode(claims, other if invalid == "signature" else key, algorithm="ES256")
    with pytest.raises(HTTPException) as exc:
        identity(HTTPAuthorizationCredentials(scheme="Bearer", credentials=token))
    assert exc.value.status_code == 401


def test_valid_jwt_requires_confirmed_provider_email(monkeypatch):
    key = ec.generate_private_key(ec.SECP256R1())
    uid = identifier()
    monkeypatch.setattr(settings(), "supabase_url", "https://identity.example.org")
    monkeypatch.setattr(
        "app.auth._jwks",
        SimpleNamespace(get_signing_key_from_jwt=lambda _: SimpleNamespace(key=key.public_key())),
    )
    claims = {
        "sub": uid,
        "session_id": identifier(),
        "email": "verified@example.org",
        "iss": "https://identity.example.org/auth/v1",
        "aud": "authenticated",
        "iat": now(),
        "exp": now() + timedelta(minutes=5),
    }
    token = jwt.encode(claims, key, algorithm="ES256")
    monkeypatch.setattr(
        "app.identity_provider.SupabaseAuth.request",
        lambda *a, **kw: {"id": uid, "email_confirmed_at": None},
    )
    with pytest.raises(HTTPException):
        identity(HTTPAuthorizationCredentials(scheme="Bearer", credentials=token))
    monkeypatch.setattr(
        "app.identity_provider.SupabaseAuth.request",
        lambda *a, **kw: {
            "id": uid,
            "email": "verified@example.org",
            "email_confirmed_at": now().isoformat(),
        },
    )
    assert identity(HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)).user_id == uid


def test_unavailable_jwks_is_not_misreported_as_an_invalid_user_identity(monkeypatch):
    monkeypatch.setattr(settings(), "supabase_url", "https://identity.example.org")

    def unavailable(_):
        raise PyJWKClientConnectionError("Fixture key service unavailable")

    monkeypatch.setattr("app.auth._jwks", SimpleNamespace(get_signing_key_from_jwt=unavailable))
    with pytest.raises(HTTPException) as exc:
        identity(HTTPAuthorizationCredentials(scheme="Bearer", credentials="fixture"))
    assert exc.value.status_code == 503
