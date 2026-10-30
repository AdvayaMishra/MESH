"""Offline, redacted R1 deployment checks; never production or privacy approval."""

import ipaddress
import json
import re
from datetime import UTC, datetime, timedelta
from typing import get_origin
from urllib.parse import urlsplit
from uuid import UUID

from cryptography.fernet import Fernet
from pydantic import ValidationError

from app.auth_policy import exact_https_endpoint
from app.core.config import Settings
from app.core.transport import authenticated_redis_tls, loopback_host


def public_https(value: str) -> bool:
    if not exact_https_endpoint(value):
        return False
    host = (urlsplit(value).hostname or "").rstrip(".")
    if host == "localhost" or host.endswith(
        (".localhost", ".invalid", ".test", ".local", ".example")
    ):
        return False
    try:
        return ipaddress.ip_address(host).is_global
    except ValueError:
        return "." in host and bool(
            re.fullmatch(r"[A-Za-z][A-Za-z0-9-]{0,62}", host.rsplit(".", 1)[-1])
        )


def trusted_proxy_addresses(value: str) -> bool:
    if not value:
        return False
    try:
        for item in value.split(","):
            item = item.strip()
            address = ipaddress.ip_address(item)
            if (
                "%" in item
                or str(address) != item
                or address.is_unspecified
                or address.is_multicast
            ):
                return False
        return True
    except ValueError:
        return False


def recent_assessment(value: object) -> bool:
    if not isinstance(value, str):
        return False
    try:
        checked = datetime.fromisoformat(value)
        if checked.tzinfo is None:
            return False
        age = datetime.now(UTC) - checked
        return -timedelta(minutes=5) <= age <= timedelta(hours=24)
    except ValueError:
        return False


def inspect_configuration(
    values: dict[str, str | None],
    *,
    public_url: str,
    require_directory: bool = False,
    require_ocr: bool = False,
    ocr_assessment: dict | None = None,
) -> dict:
    # Populate every field explicitly: the chosen file must not silently inherit
    # the operator machine's unrelated production/test credentials or policies.
    arguments = {
        name: field.get_default(call_default_factory=True)
        for name, field in Settings.model_fields.items()
    }
    for name, field in Settings.model_fields.items():
        raw = values.get(name.upper())
        if raw is not None:
            try:
                arguments[name] = (
                    json.loads(raw) if get_origin(field.annotation) in {dict, list} else raw
                )
            except (ValueError, TypeError, RecursionError):
                return {
                    "configuration_baseline_passed": False,
                    "invalid_fields": [name],
                    "production_clearance": False,
                }
    arguments["_env_file"] = None
    try:
        config = Settings(**arguments)
    except ValidationError as exc:
        return {
            "configuration_baseline_passed": False,
            "validation_errors": [
                {
                    "field": ".".join(map(str, error["loc"])) or "runtime_policy",
                    "type": error["type"],
                }
                for error in exc.errors(include_input=False, include_context=False)
            ],
            "production_clearance": False,
        }
    checks = {
        "production_mode": config.environment == "production" and not config.test_mode,
        "privileged_mfa_required": config.require_privileged_mfa,
        "backend_image_digest_pinned": bool(
            re.fullmatch(
                r"[A-Za-z0-9][A-Za-z0-9./_:-]*@sha256:[a-f0-9]{64}",
                values.get("MESH_BACKEND_IMAGE") or "",
            )
        ),
        "trusted_proxy_addresses_explicit": trusted_proxy_addresses(
            values.get("MESH_TRUSTED_PROXY_IPS") or ""
        ),
        "supabase_public_authority_configured": bool(
            config.supabase_url and config.supabase_anon_key
        ),
        "public_application_https": public_https(public_url),
        "invitation_endpoint_https": public_https(config.invitation_base_url),
        "cors_exact_https_origins": bool(config.cors_origins)
        and all(
            public_https(origin) and urlsplit(origin).path == "" for origin in config.cors_origins
        ),
        "authenticated_starttls_mail": bool(
            config.smtp_host
            and config.smtp_starttls
            and config.smtp_username
            and config.smtp_password
            and config.smtp_password.get_secret_value()
        ),
    }
    origin = urlsplit(public_url)
    invite = urlsplit(config.invitation_base_url)
    checks["invitation_uses_application_origin"] = bool(
        public_https(public_url)
        and (origin.scheme, origin.netloc.lower()) == (invite.scheme, invite.netloc.lower())
    )
    checks["cors_includes_application_origin"] = public_url.rstrip("/") in {
        item.rstrip("/") for item in config.cors_origins
    }
    checks["redis_authenticated_tls"] = authenticated_redis_tls(config.redis_url)
    try:
        Fernet(config.mail_encryption_key.get_secret_value() if config.mail_encryption_key else b"")
        checks["valid_invitation_encryption_key"] = True
    except (ValueError, TypeError):
        checks["valid_invitation_encryption_key"] = False
    if require_directory:
        checks["directory_bindings_configured"] = bool(config.scim_bindings)
        try:
            checks["directory_tenant_ids_canonical"] = bool(config.scim_bindings) and all(
                str(UUID(key)) == key for key in config.scim_bindings
            )
        except ValueError:
            checks["directory_tenant_ids_canonical"] = False
        checks["directory_conditional_writes_required"] = bool(config.scim_bindings) and all(
            binding.require_version for binding in config.scim_bindings.values()
        )
        checks["directory_lifecycle_explicitly_enabled"] = bool(config.scim_bindings) and all(
            binding.allow_provisioning and binding.allow_activation
            for binding in config.scim_bindings.values()
        )
        worker = values.get("WORKER_ORGANIZATION_ID") or ""
        checks["directory_worker_tenant_bound"] = worker in config.scim_bindings
    if require_ocr:
        checks["ocr_enabled"] = config.document_ocr_enabled
        checks["malware_service_configured"] = bool(config.clamav_host)
        checks["malware_transport_tls_or_loopback"] = bool(
            config.clamav_host and (config.clamav_tls or loopback_host(config.clamav_host))
        )
        checks["private_storage_authority_configured"] = bool(
            config.supabase_storage_key and config.supabase_storage_key.get_secret_value()
        )
        assessment = ocr_assessment or {}
        checks["configured_ocr_assessment_recent"] = recent_assessment(assessment.get("checked_at"))
        checks["configured_ocr_image_has_matching_clean_assessment"] = bool(
            assessment.get("assessment_complete") is True
            and assessment.get("passed") is True
            and assessment.get("image") == config.document_ocr_image
            and isinstance(assessment.get("immutable_image_id"), str)
            and re.fullmatch(r"sha256:[a-f0-9]{64}", assessment["immutable_image_id"])
            and type(assessment.get("vulnerability_references")) is int
            and assessment["vulnerability_references"] == 0
        )
    return {
        "checks": checks,
        "configuration_baseline_passed": all(checks.values()),
        "live_credentials_or_services_verified": False,
        "directory_lifecycle_live_verified": False,
        "identity_collection_privacy_approval_verified": False,
        "production_clearance": False,
        "limitations": [
            "Offline checks only: no DNS, TLS handshake, credential, deployment or provider-policy verification.",
            "Actual SCIM lifecycle, representative OCR evaluation, privacy/retention approval and deployed worker acceptance remain separate.",
            "No settings, users, documents or external accounts are changed.",
        ],
    }
