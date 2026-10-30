import pytest
from app.identity_provider import SupabaseAuth


@pytest.mark.parametrize("token", ["secret", "123 45", "12345a", "１２３４５６", "12345", "1" * 11])
def test_invalid_signup_or_recovery_codes_never_reach_provider(client, monkeypatch, token):
    monkeypatch.setattr(
        SupabaseAuth, "request", lambda *args, **kwargs: pytest.fail("Invalid OTP reached provider")
    )
    response = client.post(
        "/api/v1/auth/verify",
        json={"email": "pending@example.invalid", "token": token, "type": "signup"},
    )
    assert response.status_code == 422
    assert token not in response.text


@pytest.mark.parametrize("kind", ["signup", "recovery"])
def test_numeric_verification_preserves_leading_zeroes(client, monkeypatch, kind):
    calls = []

    def request(self, path, payload):
        calls.append((path, payload))
        return {
            "access_token": "fixture-access",
            "refresh_token": "fixture-refresh",
            "token_type": "bearer",
            "expires_in": 3600,
        }

    monkeypatch.setattr(SupabaseAuth, "request", request)
    response = client.post(
        "/api/v1/auth/verify",
        json={"email": "pending@example.invalid", "token": "001234", "type": kind},
    )
    assert response.status_code == 200
    assert calls == [
        ("verify", {"email": "pending@example.invalid", "token": "001234", "type": kind})
    ]
    assert response.headers["Cache-Control"] == "no-store"


@pytest.mark.parametrize(
    "route,body", [("verify", {"token": "123456"}), ("recover", {"captcha_token": "captcha"})]
)
@pytest.mark.parametrize(
    "email", ["", "not-an-email", "x@exam\nple.invalid", "x y@example.invalid"]
)
def test_recovery_and_verification_reject_malformed_email_before_provider(
    client, monkeypatch, route, body, email
):
    monkeypatch.setattr(
        SupabaseAuth,
        "request",
        lambda *args, **kwargs: pytest.fail("Invalid email reached provider"),
    )
    assert client.post("/api/v1/auth/" + route, json={"email": email, **body}).status_code == 422
