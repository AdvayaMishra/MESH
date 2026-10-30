import httpx
import pytest
from app.core.config import settings
from app.identity_provider import SupabaseAuth
from app.mfa_api import EnrollmentOutput
from fastapi import HTTPException


def test_realistic_provider_svg_size_is_allowed_only_for_enrollment(monkeypatch):
    monkeypatch.setattr(settings(), "supabase_url", "https://identity.example.org")
    monkeypatch.setattr(settings(), "supabase_anon_key", "fixture")
    body = {
        "id": "11111111-1111-4111-8111-111111111111",
        "type": "totp",
        "friendly_name": "Fixture",
        "totp": {
            "qr_code": "<svg>" + " " * 463000 + "</svg>",
            "secret": "JBSWY3DPEHPK3PXP",
            "uri": "otpauth://totp/fixture?secret=JBSWY3DPEHPK3PXP",
        },
    }
    with httpx.Client(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=body))
    ) as client:
        data = SupabaseAuth(client).request("factors", {}, token="fixture")
        assert len(EnrollmentOutput.model_validate(data).totp.qr_code) > 131072
        with pytest.raises(HTTPException) as exc:
            SupabaseAuth(client).request("user", {}, token="fixture", method="GET")
        assert exc.value.status_code == 503


def test_oversized_enrollment_response_still_fails_closed(monkeypatch):
    monkeypatch.setattr(settings(), "supabase_url", "https://identity.example.org")
    monkeypatch.setattr(settings(), "supabase_anon_key", "fixture")
    with httpx.Client(
        transport=httpx.MockTransport(
            lambda _: httpx.Response(200, json={"qr_code": "x" * 1048576})
        )
    ) as client:
        with pytest.raises(HTTPException) as exc:
            SupabaseAuth(client).request("factors", {})
    assert exc.value.status_code == 503
