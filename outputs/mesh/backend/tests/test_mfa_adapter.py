from app.auth import Identity, identity
from app.main import app
from app.models import identifier
from conftest import OWNER

FACTOR = "11111111-1111-4111-8111-111111111111"
CHALLENGE = "22222222-2222-4222-8222-222222222222"
AUTH = {"Authorization": "Bearer fixture-provider-token"}


def profile():
    return {
        "factors": [
            {
                "id": FACTOR,
                "factor_type": "totp",
                "friendly_name": "Fixture",
                "status": "verified",
                "unexpected_secret": "NEVER_SERIALIZE",
            }
        ]
    }


def test_totp_enrollment_does_not_log_or_persist_factor_secrets(client, monkeypatch, caplog):
    secret = "JBSWY3DPEHPK3PXP"

    def provider(self, path, payload, token=None, method="POST"):
        assert (
            path == "factors" and payload["factor_type"] == "totp" and payload["issuer"] == "MESH"
        )
        assert token == "fixture-provider-token"
        return {
            "id": FACTOR,
            "type": "totp",
            "friendly_name": "Fixture",
            "totp": {
                "qr_code": "<svg>fixture</svg>",
                "secret": secret,
                "uri": "otpauth://totp/MESH:fixture?secret=" + secret + "&issuer=MESH",
            },
        }

    monkeypatch.setattr("app.mfa_api.SupabaseAuth.request", provider)
    response = client.post(
        "/api/v1/auth/mfa/enroll", headers=AUTH, json={"friendly_name": "Fixture"}
    )
    assert response.status_code == 201, response.text
    assert response.json()["totp"]["secret"] == secret
    assert response.headers["Cache-Control"] == "no-store" and secret not in caplog.text


def test_mfa_factor_list_exposes_only_safe_owned_metadata(client, monkeypatch):
    monkeypatch.setattr("app.mfa_api.SupabaseAuth.request", lambda *args, **kwargs: profile())
    response = client.get("/api/v1/auth/mfa/factors", headers=AUTH)
    assert response.status_code == 200 and response.json()[0]["id"] == FACTOR
    assert "NEVER_SERIALIZE" not in response.text


def test_mfa_verify_uses_provider_challenge_and_returns_validated_tokens(client, monkeypatch):
    calls = []

    def provider(self, path, payload, token=None, method="POST"):
        calls.append(path)
        if path == "user":
            return profile()
        assert path == f"factors/{FACTOR}/verify"
        assert payload == {"challenge_id": CHALLENGE, "code": "123456"}
        return {
            "access_token": "new-access",
            "refresh_token": "new-refresh",
            "token_type": "Bearer",
            "expires_in": 3600,
        }

    monkeypatch.setattr("app.mfa_api.SupabaseAuth.request", provider)
    response = client.post(
        f"/api/v1/auth/mfa/factors/{FACTOR}/verify",
        headers=AUTH,
        json={"challenge_id": CHALLENGE, "code": "123456"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["token_type"] == "bearer" and "123456" not in response.text
    assert calls == ["user", f"factors/{FACTOR}/verify"]


def test_verified_factor_cannot_be_removed_using_only_aal1(client, monkeypatch):
    calls = []

    def provider(self, path, payload, token=None, method="POST"):
        calls.append(method)
        return profile()

    monkeypatch.setattr("app.mfa_api.SupabaseAuth.request", provider)
    response = client.delete(f"/api/v1/auth/mfa/factors/{FACTOR}", headers=AUTH)
    assert response.status_code == 403 and calls == ["GET"]
    app.dependency_overrides[identity] = lambda: Identity(OWNER, OWNER + "@example.org", "aal2")
    response = client.delete(f"/api/v1/auth/mfa/factors/{FACTOR}", headers=AUTH)
    assert response.status_code == 200 and response.json()["requires_new_login"]
    assert calls[-1] == "DELETE"


def test_totp_rejects_unknown_factors_invalid_codes_and_bad_provider_metadata(client, monkeypatch):
    monkeypatch.setattr("app.mfa_api.SupabaseAuth.request", lambda *args, **kwargs: profile())
    assert (
        client.post(f"/api/v1/auth/mfa/factors/{identifier()}/challenge", headers=AUTH).status_code
        == 404
    )
    invalid = client.post(
        f"/api/v1/auth/mfa/factors/{FACTOR}/verify",
        headers=AUTH,
        json={"challenge_id": CHALLENGE, "code": "ABCDEF"},
    )
    assert invalid.status_code == 422 and "ABCDEF" not in invalid.text
    monkeypatch.setattr("app.mfa_api.SupabaseAuth.request", lambda *args, **kwargs: {"factors": {}})
    assert client.get("/api/v1/auth/mfa/factors", headers=AUTH).status_code == 503
