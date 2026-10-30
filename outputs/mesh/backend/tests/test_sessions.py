from datetime import timedelta

from app.auth import Identity, identity
from app.core.config import settings
from app.main import app
from app.models import IdentitySession, identifier, now
from conftest import DEV, ORG_B, OWNER, headers
from fastapi import HTTPException
from pydantic import SecretStr
from sqlalchemy import select


def login_session(user, session):
    app.dependency_overrides[identity] = lambda: Identity(
        user,
        user + "@example.org",
        "aal1",
        session,
        now() + timedelta(hours=1),
    )


def test_session_revocation_blocks_unexpired_identity_across_organizations(client, db, monkeypatch):
    monkeypatch.setattr(settings(), "auth_rate_secret", SecretStr("a" * 48))
    sid_a, sid_b = identifier(), identifier()
    login_session(OWNER, sid_a)
    assert client.get("/api/v1/organizations/current", headers=headers()).status_code == 200
    login_session(OWNER, sid_b)
    assert client.get("/api/v1/organizations/current", headers=headers(ORG_B)).status_code == 200
    sessions = client.get("/api/v1/users/me/sessions").json()
    assert len(sessions) == 2
    previous = next(row for row in sessions if not row["current"])
    assert client.delete("/api/v1/users/me/sessions/" + previous["id"]).status_code == 200
    login_session(OWNER, sid_a)
    assert client.get("/api/v1/organizations/current", headers=headers(ORG_B)).status_code == 401
    assert client.get("/api/v1/users/me/sessions").status_code == 401
    row = db.scalar(select(IdentitySession).where(IdentitySession.provider_session_id == sid_a))
    assert row.revoked_at is not None


def test_session_inventory_is_self_only_and_does_not_expose_ip_or_tokens(client, db, monkeypatch):
    monkeypatch.setattr(settings(), "auth_rate_secret", SecretStr("a" * 48))
    login_session(OWNER, identifier())
    owner = client.get("/api/v1/users/me/sessions").json()[0]
    assert "ip_digest" not in owner and "provider_session_id" not in owner
    assert "access_token" not in owner and "refresh_token" not in owner
    login_session(DEV, identifier())
    own = client.get("/api/v1/users/me/sessions").json()
    assert len(own) == 1 and own[0]["id"] != owner["id"]
    assert client.delete("/api/v1/users/me/sessions/" + owner["id"]).status_code == 404
    assert (
        db.scalar(select(IdentitySession).where(IdentitySession.id == owner["id"])).revoked_at
        is None
    )


def test_revoke_others_preserves_the_current_session(client, monkeypatch):
    monkeypatch.setattr(settings(), "auth_rate_secret", SecretStr("a" * 48))
    for sid in (identifier(), identifier()):
        login_session(OWNER, sid)
        assert client.get("/api/v1/users/me/sessions").status_code == 200
    response = client.post("/api/v1/users/me/sessions/revoke-others")
    assert response.status_code == 200 and response.json()["revoked"] == 1
    rows = client.get("/api/v1/users/me/sessions").json()
    assert next(row for row in rows if row["current"])["revoked_at"] is None


def test_provider_logout_failure_does_not_undo_local_session_revocation(client, monkeypatch):
    monkeypatch.setattr(settings(), "auth_rate_secret", SecretStr("a" * 48))
    login_session(OWNER, identifier())
    assert client.get("/api/v1/users/me/sessions").status_code == 200

    def unavailable(*args, **kwargs):
        raise HTTPException(503, "Provider unavailable")

    monkeypatch.setattr("app.api.SupabaseAuth.request", unavailable)
    response = client.post("/api/v1/auth/logout", headers={"Authorization": "Bearer fixture"})
    assert response.status_code == 200
    assert response.json() == {"mesh_sessions_revoked": 1, "provider_logout": "unavailable"}
    assert client.get("/api/v1/users/me/sessions").status_code == 401
