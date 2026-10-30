import re
from decimal import Decimal
from functools import lru_cache
from pathlib import PurePosixPath, PureWindowsPath
from typing import Annotated
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator, model_validator
from pydantic_core import PydanticCustomError
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url

from app.core.transport import authenticated_redis_tls, loopback_host


class SCIMBinding(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    base_url: str
    token: SecretStr = Field(min_length=1)

    allow_activation: bool = False
    allow_provisioning: bool = False
    require_version: bool = True

    @field_validator("base_url")
    @classmethod
    def endpoint(cls, value: str) -> str:
        parts = urlsplit(value)
        if (
            parts.scheme != "https"
            or not parts.hostname
            or parts.username
            or parts.password
            or parts.query
            or parts.fragment
        ):
            raise ValueError("SCIM requires a fixed HTTPS base URL without embedded credentials")
        return value.rstrip("/")


class AIUsagePolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    provider: str = Field(pattern=r"^(gateway|ollama)$")
    model: str = Field(min_length=1, max_length=100)
    monthly_requests: int = Field(default=500, ge=1, le=1000000)
    monthly_input_units: int = Field(default=1000000, ge=4096, le=1000000000)
    monthly_output_units: int = Field(default=200000, ge=800, le=1000000000)
    input_price_per_million: Decimal | None = Field(default=None, ge=0, le=100000)
    output_price_per_million: Decimal | None = Field(default=None, ge=0, le=100000)
    currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    monthly_cost_limit: Decimal | None = Field(default=None, ge=0, le=100000000)

    @model_validator(mode="after")
    def pricing(self):
        values = (self.input_price_per_million, self.output_price_per_million, self.currency)
        if any(value is not None for value in values) and not all(
            value is not None for value in values
        ):
            raise ValueError("Both token rates and a currency are required for pricing")
        if self.monthly_cost_limit is not None and self.currency is None:
            raise ValueError("A cost admission limit requires trusted pricing")
        return self


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", hide_input_in_errors=True)
    environment: str = "development"
    database_url: str = Field(
        default="postgresql+psycopg://mesh:mesh@localhost:5432/mesh", repr=False
    )
    supabase_url: str = ""
    supabase_anon_key: str = ""
    jwt_audience: str = "authenticated"
    require_privileged_mfa: bool = False
    cors_origins: list[str] = ["http://localhost:3000"]
    redis_url: str = "redis://localhost:6379/0"
    auth_rate_secret: SecretStr | None = None
    max_request_bytes: int = 262144
    test_mode: bool = False
    smtp_host: str = ""
    smtp_port: int = Field(default=1025, ge=1, le=65535)
    smtp_from: str = "mesh@localhost"
    invitation_base_url: str = "http://localhost:3000/invitations/accept"
    github_app_id: str = ""
    github_private_key: SecretStr | None = None
    github_installations: dict[str, str] = {}
    github_webhook_secret: SecretStr | None = None
    github_webhook_previous_secret: SecretStr | None = None
    github_scan_actors: dict[str, str] = {}
    scanner_image: str = "mesh-scanner:local"
    docker_executable: str = "/usr/bin/docker"
    mail_encryption_key: SecretStr | None = None
    smtp_username: str = ""
    smtp_password: SecretStr | None = None
    smtp_starttls: bool = True
    supabase_storage_key: SecretStr | None = None
    clamav_host: str = ""
    clamav_port: int = Field(default=3310, ge=1, le=65535)
    clamav_tls: bool = False
    clamav_ca_file: str = ""
    clamav_tls_server_name: str = ""
    document_ocr_enabled: bool = False
    document_ocr_key: SecretStr | None = None
    document_ocr_image: str = "mesh-ocr:local"
    ai_provider: str = "local"
    ai_model: str = ""
    ai_url: str = ""
    ai_api_key: SecretStr | None = None
    ai_allow_external: bool = False
    ai_policies: dict[str, AIUsagePolicy] = {}
    aws_role_bindings: dict[str, str] = {}
    aws_billing_role_bindings: dict[str, str] = {}
    aws_key_max_age_days: int = Field(default=90, ge=1, le=3650)
    scim_bindings: dict[str, SCIMBinding] = {}
    telemetry_retention_days: dict[str, Annotated[int, Field(ge=30, le=3650)]] = {}

    @field_validator("scim_bindings")
    @classmethod
    def unique_scim_authorities(cls, value):
        endpoints = [binding.base_url.lower() for binding in value.values()]
        if len(endpoints) != len(set(endpoints)):
            raise ValueError("A SCIM authority must be bound to only one organization")
        return value

    @model_validator(mode="after")
    def validate_runtime(self) -> "Settings":
        if self.clamav_tls_server_name and not re.fullmatch(
            r"[A-Za-z0-9][A-Za-z0-9.-]{0,252}", self.clamav_tls_server_name
        ):
            raise ValueError("ClamAV TLS server name must be a fixed DNS name")
        if self.clamav_ca_file and not (
            PurePosixPath(self.clamav_ca_file).is_absolute()
            or PureWindowsPath(self.clamav_ca_file).is_absolute()
        ):
            raise ValueError("ClamAV CA file must be an absolute operator-configured path")
        if (
            self.environment == "production"
            and self.clamav_host
            and not self.clamav_tls
            and not loopback_host(self.clamav_host)
        ):
            raise PydanticCustomError(
                "production_malware_tls",
                "Production remote malware screening requires verified TLS or a loopback TLS sidecar",
            )
        invitation_url = urlsplit(self.invitation_base_url)
        if (
            invitation_url.scheme not in {"http", "https"}
            or not invitation_url.hostname
            or invitation_url.username is not None
            or invitation_url.password is not None
            or invitation_url.query
            or invitation_url.fragment
            or any(character in self.invitation_base_url for character in "?#\\")
            or any(ord(character) <= 32 for character in self.invitation_base_url)
        ):
            raise ValueError(
                "Invitation URL requires a fixed HTTP(S) endpoint without credentials, query or fragment"
            )
        if self.environment == "production" and self.smtp_host and invitation_url.scheme != "https":
            raise ValueError("Production invitation links require HTTPS")
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9./_:@-]{0,255}", self.document_ocr_image):
            raise ValueError("Invalid OCR image reference")
        if self.document_ocr_enabled:
            from cryptography.fernet import Fernet

            try:
                Fernet(self.document_ocr_key.get_secret_value() if self.document_ocr_key else b"")
            except (ValueError, TypeError):
                raise ValueError("OCR requires an independent valid encryption key") from None
            if self.mail_encryption_key and self.document_ocr_key == self.mail_encryption_key:
                raise ValueError("OCR and invitation mail must use separate encryption keys")
            if self.environment == "production" and not re.fullmatch(
                r".+@sha256:[a-f0-9]{64}", self.document_ocr_image
            ):
                raise ValueError("Production OCR requires a digest-pinned image")
        if self.database_url.startswith("postgresql://"):
            self.database_url = self.database_url.replace(
                "postgresql://", "postgresql+psycopg://", 1
            )
        try:
            database = make_url(self.database_url)
        except Exception:
            raise ValueError("Invalid database connection configuration") from None
        if database.get_backend_name() not in {"postgresql", "sqlite"}:
            raise ValueError("Only PostgreSQL and explicit SQLite tests are supported")
        if not (
            PurePosixPath(self.docker_executable).is_absolute()
            or PureWindowsPath(self.docker_executable).is_absolute()
        ):
            raise ValueError("Docker executable must be an absolute operator-configured path")
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9./_:@-]{0,255}", self.scanner_image):
            raise ValueError("Invalid scanner image reference")
        if self.database_url.startswith("sqlite") and not self.test_mode:
            raise ValueError("SQLite is allowed only for tests")
        if self.supabase_url and not self.supabase_url.startswith("https://"):
            raise ValueError("Supabase must use HTTPS")
        if "*" in self.cors_origins:
            raise ValueError("CORS must enumerate origins")
        if self.environment == "production" and (not self.supabase_url or self.test_mode):
            raise ValueError("Production requires Supabase and forbids test mode")
        if self.environment == "production" and (
            database.get_backend_name() != "postgresql"
            or database.query.get("sslmode") != "verify-full"
            or not database.query.get("sslrootcert")
        ):
            raise ValueError(
                "Production database connections require verified TLS and a trusted CA"
            )
        if self.environment == "production" and not self.require_privileged_mfa:
            raise ValueError("Production requires privileged MFA enforcement")
        if self.environment == "production" and (
            self.auth_rate_secret is None or len(self.auth_rate_secret.get_secret_value()) < 32
        ):
            raise ValueError(
                "Production requires an independent authentication limiter secret of at least 32 characters"
            )
        if (
            self.environment == "production"
            and self.smtp_host
            and (not self.smtp_starttls or not self.smtp_username or not self.smtp_password)
        ):
            raise ValueError("Production SMTP requires authenticated STARTTLS")
        if self.environment == "production" and not authenticated_redis_tls(self.redis_url):
            raise PydanticCustomError(
                "production_redis_tls",
                "Production Redis requires authenticated TLS with certificate and hostname verification",
            )
        return self


@lru_cache
def settings() -> Settings:
    return Settings()
