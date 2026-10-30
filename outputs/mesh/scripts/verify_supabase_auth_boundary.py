"""Live negative Auth checks only. Does not create users, send email or enroll MFA."""

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import httpx
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
sys.path.insert(0, str(ROOT / "backend"))

from app.core.config import settings  # noqa: E402
from app.identity_provider import Refresh, SupabaseAuth  # noqa: E402
from fastapi import HTTPException  # noqa: E402
from pydantic import SecretStr  # noqa: E402


def verify():
    config = settings()
    checks = {}
    with httpx.Client(timeout=15, follow_redirects=False) as client:
        base = config.supabase_url.rstrip("/") + "/auth/v1/"
        headers = {"apikey": config.supabase_anon_key}
        for name, extra in (
            ("public_api_key_does_not_authenticate_user", {}),
            (
                "invalid_bearer_does_not_authenticate_user",
                {"Authorization": "Bearer mesh-invalid-test-token"},
            ),
        ):
            response = client.get(base + "user", headers={**headers, **extra})
            assert response.status_code in {401, 403}
            checks[name] = "passed"
        keys = client.get(base + ".well-known/jwks.json", headers=headers)
        keys.raise_for_status()
        assert any(
            key.get("alg") in {"ES256", "RS256"} and "d" not in key for key in keys.json()["keys"]
        )
        checks["asymmetric_public_jwks_available"] = "passed"
        try:
            SupabaseAuth(client).refresh(
                Refresh(refresh_token=SecretStr("mesh-invalid-refresh-fixture"))
            )
        except HTTPException as exc:
            assert exc.status_code == 401
            checks["invalid_refresh_is_sanitized_and_rejected"] = "passed"
        else:
            raise AssertionError("Invalid refresh token was accepted")
    return {
        "verified_at_utc": datetime.now(UTC).isoformat(),
        "checks": checks,
        "pending": [
            "Signup/email OTP/login/recovery/valid refresh need a controlled test account and inbox/CAPTCHA configuration.",
            "MFA enrollment/challenge/verification/removal need that authenticated test account.",
            "Positive private Storage flows need backend Storage authority and a confirmed test user; ClamAV must run for upload acceptance.",
        ],
        "no_user_created_or_email_sent": True,
    }


if __name__ == "__main__":
    try:
        report = verify()
    except Exception as exc:
        print(json.dumps({"failed": type(exc).__name__}))
        raise SystemExit(1) from None
    (ROOT / "docs/supabase-auth-boundary-results.json").write_text(
        json.dumps(report, indent=2) + "\n"
    )
    print(json.dumps(report, indent=2))
