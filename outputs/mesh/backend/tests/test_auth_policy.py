import importlib.util
import json
from pathlib import Path

import httpx
import pytest
from app.auth_policy import evaluate_auth_policy, exact_https_endpoint


def baseline():
    return {
        "external_email_enabled": True,
        "disable_signup": False,
        "mailer_autoconfirm": False,
        "security_captcha_enabled": True,
        "refresh_token_rotation_enabled": True,
        "mfa_totp_enroll_enabled": True,
        "mfa_totp_verify_enabled": True,
        "jwt_exp": 3600,
        "password_min_length": 12,
        "security_refresh_token_reuse_interval": 10,
        "mailer_otp_exp": 600,
        "mailer_otp_length": 6,
        "smtp_max_frequency": 60,
        "smtp_host": "smtp.example.invalid",
        "smtp_user": "private-user",
        "smtp_admin_email": "private@example.invalid",
        "site_url": "https://mesh.example.invalid",
        "uri_allow_list": "https://mesh.example.invalid/auth/callback",
        "mailer_templates_confirmation_content": "Your code: {{ .Token }}",
        "mailer_templates_recovery_content": "Your code: {{ .Token }}",
        "smtp_pass": "private-password",
        "security_captcha_secret": "private-captcha-secret",
    }


def test_policy_snapshot_is_redacted_and_never_claims_live_acceptance():
    report = evaluate_auth_policy(baseline())
    assert report["configuration_baseline_passed"]
    assert not report["production_clearance"]
    assert not report["live_journeys_verified"]
    assert "private" not in json.dumps(report)


def test_missing_policy_fields_remain_unknown():
    report = evaluate_auth_policy({})
    assert set(report["checks"].values()) == {"unknown"}
    assert not report["configuration_baseline_passed"]


@pytest.mark.parametrize("field", list(baseline()))
def test_missing_security_fields_do_not_receive_synthetic_defaults(field):
    config = baseline()
    del config[field]
    result = evaluate_auth_policy(config)
    if field not in {"smtp_pass", "security_captcha_secret"}:
        assert "unknown" in result["checks"].values()
        assert not result["configuration_baseline_passed"]


@pytest.mark.parametrize(
    "value",
    [
        "http://mesh.example",
        "https://*.example",
        "https://user:secret@example.org",
        "https://example.org#",
        "https://example.org?",
        "https://example.org\\path",
        "https://example.org:broken",
        None,
        1,
    ],
)
def test_redirects_require_exact_credential_free_https(value):
    assert not exact_https_endpoint(value)


@pytest.mark.parametrize(
    "field,value",
    [
        ("jwt_exp", True),
        ("mailer_otp_exp", 3600),
        ("password_min_length", 6),
        ("mailer_autoconfirm", True),
        ("security_captcha_enabled", "true"),
        ("refresh_token_rotation_enabled", False),
    ],
)
def test_unsafe_or_malformed_policy_fails(field, value):
    config = baseline()
    config[field] = value
    assert not evaluate_auth_policy(config)["configuration_baseline_passed"]


def policy_driver():
    path = Path(__file__).resolve().parents[2] / "scripts/verify_supabase_auth_policy.py"
    spec = importlib.util.spec_from_file_location("mesh_policy_driver", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("status", [302, 401, 403, 429, 503])
def test_management_read_is_fixed_get_no_redirect_or_secret_output(status):
    requests = []

    def handler(request):
        requests.append(request)
        assert request.method == "GET"
        assert (
            str(request.url)
            == "https://api.supabase.com/v1/projects/abcdefghijklmnopqrst/config/auth"
        )
        return httpx.Response(
            status,
            json={"private": "private-provider-secret"},
            headers={"Location": "https://attacker.invalid"},
        )

    with httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True) as client:
        result = policy_driver().inspect_policy("abcdefghijklmnopqrst", "private-token", client)
    assert result["status"] == "management_read_failed"
    assert len(requests) == 1
    assert "private" not in json.dumps(result)


def test_management_missing_authority_makes_no_request():
    def forbidden(request):
        pytest.fail("Missing management authority must not contact provider")

    with httpx.Client(transport=httpx.MockTransport(forbidden)) as client:
        report = policy_driver().inspect_policy("abcdefghijklmnopqrst", "", client)
    assert report["status"] == "management_authority_missing"


def test_shipped_templates_use_numeric_code_without_executable_or_token_urls():
    root = Path(__file__).resolve().parents[2] / "supabase/templates"
    for name in ("confirmation", "recovery"):
        content = (root / (name + ".html")).read_text(encoding="utf-8")
        assert "{{ .Token }}" in content
        assert "ConfirmationURL" not in content
        assert "<script" not in content
        assert "href=" not in content
