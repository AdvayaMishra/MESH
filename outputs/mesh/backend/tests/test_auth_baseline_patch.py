import pytest
from app.auth_policy import auth_baseline_patch


def current(**updates):
    return {
        "password_min_length": 6,
        "mailer_otp_length": 8,
        "smtp_max_frequency": 60,
        "mailer_otp_exp": 3600,
        "jwt_exp": 3600,
        "security_refresh_token_reuse_interval": 10,
        **updates,
    }


def test_patch_strengthens_controls_without_changing_existing_eight_digit_otp():
    patch = auth_baseline_patch(current(), "confirmation", "recovery")
    assert patch["password_min_length"] == 12
    assert patch["mailer_otp_exp"] == 600
    assert "mailer_otp_length" not in patch


def test_patch_preserves_stronger_controls_and_does_not_mutate_input():
    config = current(
        password_min_length=16,
        mailer_otp_length=10,
        smtp_max_frequency=120,
        mailer_otp_exp=300,
        jwt_exp=900,
        security_refresh_token_reuse_interval=0,
    )
    before = config.copy()
    patch = auth_baseline_patch(config, "confirmation", "recovery")
    assert config == before
    assert not set(before).intersection(patch)


def test_patch_never_touches_credentials_provider_selection_domains_or_signup_availability():
    config = current(
        smtp_pass="private",
        security_captcha_secret="private",
        site_url="http://localhost:3000",
        disable_signup=True,
    )
    patch = auth_baseline_patch(config, "confirmation", "recovery")
    assert not {
        "smtp_pass",
        "smtp_host",
        "security_captcha_enabled",
        "security_captcha_secret",
        "site_url",
        "uri_allow_list",
        "disable_signup",
        "sessions_timebox",
        "sessions_inactivity_timeout",
    }.intersection(patch)


@pytest.mark.parametrize("bad", [None, True, "600", -1])
def test_unverified_numeric_policy_fails_before_patch(bad):
    with pytest.raises(ValueError):
        auth_baseline_patch(current(mailer_otp_exp=bad), "confirmation", "recovery")


def test_patch_is_idempotent_after_readback():
    config = current()
    config.update(auth_baseline_patch(config, "confirmation", "recovery"))
    assert auth_baseline_patch(config, "confirmation", "recovery") == {}
