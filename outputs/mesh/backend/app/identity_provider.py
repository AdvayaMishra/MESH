"""Single password authority: Supabase Auth. No application password hashes."""

import json
import re
from typing import Literal

import httpx
from fastapi import HTTPException
from pydantic import Field, SecretStr, ValidationError, field_validator

from app.core.config import settings
from app.schemas import Input


class AuthCredentials(Input):
    email: str = Field(min_length=3, max_length=254, pattern=r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
    password: SecretStr = Field(min_length=12, max_length=128)
    captcha_token: SecretStr = Field(min_length=1, max_length=4096)


def normalize_owner_name(value: str) -> str:
    value = value.strip()
    if not value or len(value) > 200 or any(not char.isprintable() for char in value):
        raise ValueError("Owner name must contain 1 to 200 printable characters")
    return value


class Signup(AuthCredentials):
    # Display metadata only. Membership roles never come from this field.
    owner_name: str | None = Field(default=None, min_length=1, max_length=200)

    @field_validator("owner_name")
    @classmethod
    def valid_owner_name(cls, value: str | None) -> str | None:
        return normalize_owner_name(value) if value is not None else None


class Login(AuthCredentials):
    pass


def owner_name_from_profile(profile: dict) -> str | None:
    metadata = profile.get("user_metadata")
    value = metadata.get("owner_name") if isinstance(metadata, dict) else None
    if not isinstance(value, str):
        return None
    try:
        return normalize_owner_name(value)
    except ValueError:
        return None


class Verify(Input):
    email: str = Field(min_length=3, max_length=254, pattern=r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
    token: SecretStr = Field(min_length=6, max_length=10)
    type: Literal["signup", "recovery"] = "signup"

    @field_validator("token")
    @classmethod
    def numeric_otp(cls, value: SecretStr) -> SecretStr:
        if not re.fullmatch(r"[0-9]{6,10}", value.get_secret_value()):
            raise ValueError("Verification requires a numeric one-time code")
        return value


class Refresh(Input):
    refresh_token: SecretStr = Field(min_length=1, max_length=8192)


class Recover(Input):
    email: str = Field(min_length=3, max_length=254, pattern=r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
    captcha_token: SecretStr = Field(min_length=1, max_length=4096)


class ResendSignup(Input):
    email: str = Field(min_length=3, max_length=254, pattern=r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
    captcha_token: SecretStr = Field(min_length=1, max_length=4096)


class Tokens(Input):
    access_token: str = Field(min_length=1, max_length=16384)
    refresh_token: str = Field(min_length=1, max_length=8192)
    token_type: Literal["bearer"]
    expires_in: int = Field(gt=0, le=604800)


def provider_tokens(result: dict) -> Tokens:
    """A malformed upstream response is an integration failure, never a user traceback."""
    try:
        values = {key: result[key] for key in Tokens.model_fields}
        if isinstance(values["token_type"], str):
            values["token_type"] = values["token_type"].lower()
        return Tokens.model_validate(values)
    except (KeyError, TypeError, ValidationError):
        raise HTTPException(503, "Identity provider returned an invalid session") from None


class SupabaseAuth:
    def __init__(self, client: httpx.Client | None = None):
        self.client = client

    def request(
        self, path: str, payload: dict, token: str | None = None, method: str = "POST"
    ) -> dict:
        config = settings()
        if not config.supabase_url or not config.supabase_anon_key:
            raise HTTPException(503, "Identity provider is not configured")
        headers = {"apikey": config.supabase_anon_key}
        if token:
            headers["Authorization"] = "Bearer " + token
        # Provider-generated TOTP QR SVGs can exceed the ordinary Auth JSON cap.
        # Keep the exception confined to the fixed enrollment operation.
        response_limit = 1048576 if method == "POST" and path == "factors" else 131072

        def receive(client: httpx.Client) -> dict:
            with client.stream(
                method,
                config.supabase_url.rstrip("/") + "/auth/v1/" + path,
                json=payload if method != "GET" else None,
                headers=headers,
                follow_redirects=False,
                timeout=10,
            ) as response:
                if response.status_code == 429:
                    raise HTTPException(429, "Identity provider rate limit reached")
                if response.status_code >= 500 or 300 <= response.status_code < 400:
                    raise HTTPException(503, "Identity provider unavailable")
                if response.status_code >= 400:
                    raise HTTPException(401, "Identity operation was not accepted")
                content = bytearray()
                for chunk in response.iter_bytes(chunk_size=16384):
                    content.extend(chunk)
                    if len(content) > response_limit:
                        raise ValueError("Oversized identity response")
                result = json.loads(content) if content else {}
                if not isinstance(result, dict):
                    raise ValueError("Invalid identity response")
                return result

        try:
            if self.client:
                return receive(self.client)
            with httpx.Client(timeout=10, follow_redirects=False) as client:
                return receive(client)
        except (httpx.HTTPError, ValueError, RecursionError):
            raise HTTPException(503, "Identity provider unavailable") from None

    def signup(self, data: Signup) -> None:
        payload = {
            "email": data.email,
            "password": data.password.get_secret_value(),
            "gotrue_meta_security": {"captcha_token": data.captcha_token.get_secret_value()},
        }
        if data.owner_name is not None:
            payload["data"] = {"owner_name": data.owner_name}
        self.request(
            "signup",
            payload,
        )

    def login(self, data: Login) -> Tokens:
        result = self.request(
            "token?grant_type=password",
            {
                "email": data.email,
                "password": data.password.get_secret_value(),
                "gotrue_meta_security": {"captcha_token": data.captcha_token.get_secret_value()},
            },
        )
        return provider_tokens(result)

    def resend_signup(self, data: ResendSignup) -> None:
        self.request(
            "resend",
            {
                "type": "signup",
                "email": data.email,
                "gotrue_meta_security": {"captcha_token": data.captcha_token.get_secret_value()},
            },
        )

    def refresh(self, data: Refresh) -> Tokens:
        result = self.request(
            "token?grant_type=refresh_token",
            {"refresh_token": data.refresh_token.get_secret_value()},
        )
        return provider_tokens(result)
