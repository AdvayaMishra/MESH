import json
from datetime import UTC, datetime, timedelta

import pytest
from app.production_readiness import inspect_configuration, public_https, recent_assessment
from cryptography.fernet import Fernet


def production(**updates):
    return {
        "ENVIRONMENT": "production",
        "TEST_MODE": "false",
        "DATABASE_URL": "postgresql+psycopg://runtime:private-database-password@database.example.com/mesh?sslmode=verify-full&sslrootcert=system",
        "SUPABASE_URL": "https://identity.example.com",
        "SUPABASE_ANON_KEY": "fixture-public-key",
        "REQUIRE_PRIVILEGED_MFA": "true",
        "AUTH_RATE_SECRET": "a" * 48,
        "MESH_BACKEND_IMAGE": "registry.example.com/mesh-backend@sha256:" + "b" * 64,
        "MESH_TRUSTED_PROXY_IPS": "127.0.0.1",
        "WORKER_ORGANIZATION_ID": "11111111-1111-4111-8111-111111111111",
        "CLAMAV_TLS": "true",
        "REDIS_URL": "rediss://default:private-redis-password@cache.example.com:6380/0",
        "SMTP_HOST": "smtp.example.com",
        "SMTP_PORT": "587",
        "SMTP_FROM": "fixture@example.com",
        "SMTP_STARTTLS": "true",
        "SMTP_USERNAME": "private-smtp-user",
        "SMTP_PASSWORD": "private-smtp-password",
        "MAIL_ENCRYPTION_KEY": Fernet.generate_key().decode(),
        "INVITATION_BASE_URL": "https://app.example.com/invitations/accept",
        "CORS_ORIGINS": '["https://app.example.com"]',
        **updates,
    }


def inspect(values, **kwargs):
    return inspect_configuration(values, public_url="https://app.example.com", **kwargs)


def test_configured_baseline_never_claims_live_services_or_release_approval():
    report = inspect(production())
    assert report["configuration_baseline_passed"]
    assert not report["production_clearance"]
    assert not report["live_credentials_or_services_verified"]
    assert not report["identity_collection_privacy_approval_verified"]
    assert "private-" not in json.dumps(report)


@pytest.mark.parametrize(
    "value",
    [
        None,
        "not-a-date",
        (datetime.now(UTC) - timedelta(hours=25)).isoformat(),
        (datetime.now(UTC) + timedelta(minutes=10)).isoformat(),
        datetime.now().isoformat(),
    ],
)
def test_image_assessments_must_be_recent_timezone_aware_and_not_future_dated(value):
    assert not recent_assessment(value)


def test_complete_technical_ocr_config_still_cannot_approve_privacy_or_release():
    image = "registry.example.com/mesh-ocr@sha256:" + "a" * 64
    values = production(
        DOCUMENT_OCR_ENABLED="true",
        DOCUMENT_OCR_KEY=Fernet.generate_key().decode(),
        DOCUMENT_OCR_IMAGE=image,
        CLAMAV_HOST="scanner.example.com",
        SUPABASE_STORAGE_KEY="private-storage-key",
    )
    assessment = {
        "image": image,
        "assessment_complete": True,
        "passed": True,
        "immutable_image_id": "sha256:" + "b" * 64,
        "vulnerability_references": 0,
        "checked_at": datetime.now(UTC).isoformat(),
    }
    report = inspect(values, require_ocr=True, ocr_assessment=assessment)
    assert report["configuration_baseline_passed"]
    assert not report["production_clearance"]
    assert not report["identity_collection_privacy_approval_verified"]


def test_selected_file_does_not_inherit_host_credentials_or_flags(monkeypatch):
    monkeypatch.setenv("SMTP_HOST", "private-host-should-not-be-used")
    monkeypatch.setenv("SMTP_PASSWORD", "private-host-password")
    monkeypatch.setenv("REQUIRE_PRIVILEGED_MFA", "true")
    report = inspect({})
    assert not report["configuration_baseline_passed"]
    assert not report["checks"]["authenticated_starttls_mail"]
    assert not report["checks"]["privileged_mfa_required"]
    assert "private-host" not in json.dumps(report)


@pytest.mark.parametrize(
    "url",
    [
        "http://app.example.com",
        "https://localhost",
        "https://127.0.0.1",
        "https://10.0.0.1",
        "https://app.local",
        "https://app.invalid",
        "https://app.example",
        "https://user:private-password@app.example.com",
        "https://app.example.com#",
        "https://*.example.com",
    ],
)
def test_production_endpoint_rejects_local_ambiguous_and_credential_urls(url):
    assert not public_https(url)


@pytest.mark.parametrize(
    "url", ["https://localhost.", "https://127.0.0.1.", "https://127.1", "https://0x7f.0.0.1"]
)
def test_alternate_loopback_spellings_are_not_public_production_hosts(url):
    assert not public_https(url)


@pytest.mark.parametrize(
    "query",
    [
        "ssl_cert_reqs=none",
        "ssl_cert_reqs=optional",
        "ssl_check_hostname=false",
        "ssl_check_hostname=0",
        "ssl_check_hostname=true&ssl_check_hostname=false",
    ],
)
def test_redis_tls_verification_cannot_be_disabled_through_url_options(query):
    report = inspect(
        production(REDIS_URL="rediss://default:private-password@cache.example.com:6380/0?" + query)
    )
    assert not report["configuration_baseline_passed"]
    assert any(error["type"] == "production_redis_tls" for error in report["validation_errors"])


@pytest.mark.parametrize("proxy", ["*", "0.0.0.0", "127.0.0.1/8", "private-host", "127.0.0.1,*"])
def test_production_proxy_trust_cannot_be_wildcard_or_ambiguous(proxy):
    assert not inspect(production(MESH_TRUSTED_PROXY_IPS=proxy))["checks"][
        "trusted_proxy_addresses_explicit"
    ]


def test_mutable_backend_image_is_not_production_configuration():
    assert not inspect(production(MESH_BACKEND_IMAGE="mesh-backend:latest"))["checks"][
        "backend_image_digest_pinned"
    ]


@pytest.mark.parametrize(
    "overrides,failed",
    [
        ({"CORS_ORIGINS": '["https://other.example.com"]'}, "cors_includes_application_origin"),
        ({"CORS_ORIGINS": '["https://app.example.com/path"]'}, "cors_exact_https_origins"),
        ({"CORS_ORIGINS": '["https://app.example.com/"]'}, "cors_exact_https_origins"),
        (
            {"INVITATION_BASE_URL": "https://other.example.com/accept"},
            "invitation_uses_application_origin",
        ),
        ({"MAIL_ENCRYPTION_KEY": "private-invalid-key"}, "valid_invitation_encryption_key"),
    ],
)
def test_unsafe_deployment_inputs_fail_named_checks_without_values(overrides, failed):
    report = inspect(production(**overrides))
    assert not report["configuration_baseline_passed"]
    assert not report["checks"][failed]
    assert "private-" not in json.dumps(report)


def test_invalid_structured_input_reports_field_only():
    report = inspect(production(SCIM_BINDINGS="private-malformed-json"))
    assert report["invalid_fields"] == ["scim_bindings"]
    assert "private-malformed-json" not in json.dumps(report)


def test_production_validation_errors_do_not_echo_secret_inputs():
    report = inspect(
        production(
            DATABASE_URL="postgresql://runtime:private-database-password@database.example.com/mesh"
        )
    )
    assert not report["configuration_baseline_passed"]
    assert "private-database-password" not in json.dumps(report)


def test_required_directory_has_no_synthetic_fallback():
    report = inspect(production(), require_directory=True)
    assert not report["checks"]["directory_bindings_configured"]
    assert not report["configuration_baseline_passed"]


def test_configured_directory_is_still_not_live_acceptance():
    binding = {
        "11111111-1111-4111-8111-111111111111": {
            "base_url": "https://directory.example.com/scim/v2",
            "token": "private-directory-token",
            "allow_activation": True,
            "allow_provisioning": True,
        }
    }
    report = inspect(production(SCIM_BINDINGS=json.dumps(binding)), require_directory=True)
    assert report["configuration_baseline_passed"]
    assert not report["directory_lifecycle_live_verified"]
    assert "private-directory-token" not in json.dumps(report)


def test_directory_requires_canonical_tenant_and_conditional_updates():
    binding = {
        "not-a-tenant": {
            "base_url": "https://directory.example.com/scim/v2",
            "token": "private-directory-token",
            "allow_activation": True,
            "allow_provisioning": True,
            "require_version": False,
        }
    }
    report = inspect(production(SCIM_BINDINGS=json.dumps(binding)), require_directory=True)
    assert not report["checks"]["directory_tenant_ids_canonical"]
    assert not report["checks"]["directory_conditional_writes_required"]


def test_required_ocr_fails_without_worker_storage_and_matching_clean_image():
    report = inspect(production(), require_ocr=True)
    assert not report["checks"]["ocr_enabled"]
    assert not report["checks"]["malware_service_configured"]
    assert not report["checks"]["configured_ocr_image_has_matching_clean_assessment"]


@pytest.mark.parametrize(
    "change",
    [
        {"image": "another-image"},
        {"passed": False},
        {"assessment_complete": False},
        {"vulnerability_references": 1},
        {"vulnerability_references": False},
    ],
)
def test_ocr_gate_rejects_stale_mismatched_or_failed_assessments(change):
    image = "registry.example.com/mesh-ocr@sha256:" + "a" * 64
    values = production(
        DOCUMENT_OCR_ENABLED="true",
        DOCUMENT_OCR_KEY=Fernet.generate_key().decode(),
        DOCUMENT_OCR_IMAGE=image,
        CLAMAV_HOST="clamav",
        SUPABASE_STORAGE_KEY="private-storage-key",
    )
    assessment = {
        "image": image,
        "assessment_complete": True,
        "passed": True,
        "immutable_image_id": "sha256:" + "b" * 64,
        "vulnerability_references": 0,
        **change,
    }
    report = inspect(values, require_ocr=True, ocr_assessment=assessment)
    assert not report["checks"]["configured_ocr_image_has_matching_clean_assessment"]
    assert not report["production_clearance"]
