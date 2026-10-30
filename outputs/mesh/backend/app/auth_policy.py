"""Redacted operator checks for R1-02, never an assertion of live inbox acceptance."""

import re
from urllib.parse import urlsplit


def auth_baseline_patch(config: dict, confirmation: str, recovery: str) -> dict:
    """Narrow, credential-free patch; preserve stronger existing numeric controls.

    SMTP, CAPTCHA secrets, domains, signing keys, paid features, session policy
    and identity records require separate inputs and are never touched here.
    """
    desired = {
        "mailer_autoconfirm": False,
        "mailer_allow_unverified_email_sign_ins": False,
        # Boolean provider policy flag; this value is not a credential.
        "refresh_token_rotation_enabled": True,  # nosec B105
        "mfa_totp_enroll_enabled": True,
        "mfa_totp_verify_enabled": True,
        "mailer_subjects_confirmation": "Confirm your MESH email",
        "mailer_subjects_recovery": "Reset your MESH password",
        "mailer_templates_confirmation_content": confirmation,
        "mailer_templates_recovery_content": recovery,
    }
    for field, target, floor in (
        ("password_min_length", 12, True),
        ("mailer_otp_length", 8, True),
        ("smtp_max_frequency", 60, True),
        ("mailer_otp_exp", 600, False),
        ("jwt_exp", 3600, False),
        ("security_refresh_token_reuse_interval", 10, False),
    ):
        value = config.get(field)
        if type(value) is not int or value < 0:
            raise ValueError("Current numeric Auth controls must be verified before configuration")
        desired[field] = max(value, target) if floor else min(value, target)
    return {key: value for key, value in desired.items() if config.get(key) != value}


def exact_https_endpoint(value: object) -> bool:
    if (
        not isinstance(value, str)
        or not value
        or any(ord(character) <= 32 or character in "*?#\\" for character in value)
    ):
        return False
    try:
        parsed = urlsplit(value)
        port = parsed.port
        return bool(
            parsed.scheme == "https"
            and parsed.hostname
            and parsed.username is None
            and parsed.password is None
            and (port is None or port > 0)
        )
    except ValueError:
        return False


def evaluate_auth_policy(config: dict) -> dict:
    """Return fixed check IDs and states only; provider config may contain secrets.

    Missing/null fields stay unknown. Numeric bounds are MESH's documented
    acceptance baseline, not Supabase defaults. A passing snapshot does not
    establish administrator approval, mailbox delivery, expiry/replay or MFA use.
    """
    checks = {}

    def check(name, field, predicate):
        checks[name] = (
            "unknown"
            if field not in config or config[field] is None
            else "passed"
            if predicate(config[field])
            else "failed"
        )

    for name, field, expected in (
        ("email_signup", "external_email_enabled", True),
        ("signup_enabled", "disable_signup", False),
        ("confirmation_required", "mailer_autoconfirm", False),
        ("captcha_enabled", "security_captcha_enabled", True),
        ("refresh_rotation", "refresh_token_rotation_enabled", True),
        ("totp_enrollment", "mfa_totp_enroll_enabled", True),
        ("totp_verification", "mfa_totp_verify_enabled", True),
    ):
        check(name, field, lambda value, expected=expected: value is expected)

    for name, field, lower, upper in (
        ("access_token_lifetime", "jwt_exp", 300, 3600),
        ("password_strength", "password_min_length", 12, 128),
        ("refresh_reuse_window", "security_refresh_token_reuse_interval", 0, 10),
        ("email_otp_lifetime", "mailer_otp_exp", 60, 600),
        ("email_otp_length", "mailer_otp_length", 6, 10),
        ("email_resend_cooldown", "smtp_max_frequency", 60, 3600),
    ):
        check(
            name, field, lambda value, lo=lower, hi=upper: type(value) is int and lo <= value <= hi
        )

    for field in ("smtp_host", "smtp_user", "smtp_admin_email"):
        check(
            field + "_present", field, lambda value: isinstance(value, str) and bool(value.strip())
        )
    check("site_url_https", "site_url", exact_https_endpoint)
    check(
        "redirect_allowlist_exact_https",
        "uri_allow_list",
        lambda value: (
            isinstance(value, str)
            and all(exact_https_endpoint(item.strip()) for item in value.split(",") if item.strip())
            and not any(not item.strip() for item in value.split(","))
            if value != ""
            else True
        ),
    )
    for kind in ("confirmation", "recovery"):
        check(
            kind + "_numeric_otp_template",
            "mailer_templates_" + kind + "_content",
            lambda value: (
                isinstance(value, str)
                and bool(re.search(r"{{\s*\.Token\s*}}", value))
                and not re.search(r"{{\s*\.(?:ConfirmationURL|TokenHash)\b", value)
            ),
        )
    return {
        "policy_version": "mesh-r1-auth-1",
        "checks": checks,
        "configuration_baseline_passed": all(state == "passed" for state in checks.values()),
        "live_journeys_verified": False,
        "production_clearance": False,
    }
