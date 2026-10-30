import smtplib
import ssl
from unittest.mock import MagicMock

import pytest
from app import mail
from app.core.config import Settings
from fastapi import HTTPException
from pydantic import SecretStr, ValidationError


@pytest.mark.parametrize(
    "url",
    [
        "javascript:alert(1)",
        "https://user:password@example.org/invite",
        "https://example.org/invite?redirect=https://other.example",
        "https://example.org/invite#fragment",
        "https://example.org/invite#",
        "https://example.org/invite?",
        "https://example.org\\other/invite",
        "https://example.org/invite\n",
        "//example.org/invite",
    ],
)
def test_invitation_endpoint_rejects_ambiguous_or_credential_bearing_urls(url):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, invitation_base_url=url)


@pytest.mark.parametrize("port", [0, -1, 65536])
def test_smtp_port_requires_a_valid_transport_port(port):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, smtp_port=port)


def test_production_mail_cannot_send_invitation_tokens_over_http():
    with pytest.raises(ValidationError, match="invitation links require HTTPS"):
        Settings(
            _env_file=None,
            environment="production",
            smtp_host="smtp.example.org",
            invitation_base_url="http://example.org/invite",
        )


def test_local_mail_accepts_loopback_invitation_links():
    config = Settings(_env_file=None, invitation_base_url="http://127.0.0.1:3000/invite")
    assert config.invitation_base_url.endswith("/invite")


@pytest.mark.parametrize("failure_stage", ["starttls", "login", "send_message"])
def test_mail_transport_failure_is_sanitized_and_stops_delivery(monkeypatch, failure_stage):
    config = Settings(
        _env_file=None,
        smtp_host="smtp.example.org",
        smtp_username="fixture-user",
        smtp_password=SecretStr("fixture-private-password"),
    )
    monkeypatch.setattr(mail, "settings", lambda: config)
    transport = MagicMock()
    transport.__enter__.return_value = transport
    getattr(transport, failure_stage).side_effect = smtplib.SMTPException(
        "fixture-private-password fixture-private-token"
    )
    monkeypatch.setattr(mail.smtplib, "SMTP", lambda *args, **kwargs: transport)
    with pytest.raises(HTTPException) as exc:
        mail.send_invitation("fixture@example.invalid", "fixture-private-token", "fixture-org")
    assert exc.value.status_code == 503
    assert exc.value.detail == "Invitation delivery failed"
    if failure_stage == "starttls":
        transport.login.assert_not_called()
    if failure_stage != "send_message":
        transport.send_message.assert_not_called()


def test_mail_uses_verified_tls_before_credentials_and_delivery(monkeypatch):
    config = Settings(
        _env_file=None,
        smtp_host="smtp.example.org",
        smtp_username="fixture-user",
        smtp_password=SecretStr("fixture-password"),
    )
    monkeypatch.setattr(mail, "settings", lambda: config)
    transport = MagicMock()
    transport.__enter__.return_value = transport
    monkeypatch.setattr(mail.smtplib, "SMTP", lambda *args, **kwargs: transport)
    mail.send_invitation("fixture@example.invalid", "fixture-token", "fixture-org")
    context = transport.starttls.call_args.kwargs["context"]
    assert context.check_hostname
    assert context.verify_mode == ssl.CERT_REQUIRED
    calls = [call[0] for call in transport.method_calls]
    assert calls == ["starttls", "login", "send_message"]
