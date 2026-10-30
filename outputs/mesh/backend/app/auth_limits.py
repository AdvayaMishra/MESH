"""Shared per-account throttling without plaintext identities in Redis keys."""

import hashlib
import hmac
import json
import time

from app.core.config import settings

AUTH_PATHS = {
    "/api/v1/auth/login",
    "/api/v1/auth/register",
    "/api/v1/auth/verify",
    "/api/v1/auth/recover",
    "/api/v1/auth/resend",
}


def account_key(body: bytes) -> str | None:
    try:
        data = json.loads(body)
    except (ValueError, UnicodeError, RecursionError):
        return None
    email = data.get("email") if isinstance(data, dict) else None
    if not isinstance(email, str) or not 3 <= len(email) <= 254:
        return None
    secret = settings().auth_rate_secret
    if secret is None or len(secret.get_secret_value()) < 32:
        raise RuntimeError("Authentication limiter key is not configured")
    digest = hmac.new(
        secret.get_secret_value().encode(), email.strip().lower().encode(), hashlib.sha256
    ).hexdigest()
    return f"mesh:auth:{digest}:{int(time.time()) // 60}"
