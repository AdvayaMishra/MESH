import json
import smtplib
import ssl
from email.message import EmailMessage
from urllib.parse import urlencode

from cryptography.fernet import Fernet
from fastapi import HTTPException

from app.core.config import settings


def queue_invitation(db, record, token: str) -> None:
    from app.models import Outbox

    config = settings()
    if not config.smtp_host or not config.mail_encryption_key:
        raise HTTPException(503, "Encrypted invitation mail delivery is not configured")
    try:
        encrypted = (
            Fernet(config.mail_encryption_key.get_secret_value().encode())
            .encrypt(json.dumps({"email": record.email, "token": token}).encode())
            .decode()
        )
    except ValueError:
        raise HTTPException(503, "Invitation encryption configuration is invalid") from None
    db.add(
        Outbox(
            organization_id=record.organization_id,
            topic="mail.invitation",
            payload={"invitation_id": record.id, "ciphertext": encrypted},
        )
    )


def send_invitation(email: str, token: str, organization_id: str) -> None:
    config = settings()
    if not config.smtp_host:
        raise HTTPException(503, "Invitation email delivery is not configured")
    message = EmailMessage()
    message["From"] = config.smtp_from
    message["To"] = email
    message["Subject"] = "MESH organization invitation"
    url = (
        config.invitation_base_url
        + "?"
        + urlencode({"token": token, "organization_id": organization_id})
    )
    message.set_content(
        f"Accept your invitation within three days: {url}\nIf unexpected, ignore this message."
    )
    try:
        with smtplib.SMTP(config.smtp_host, config.smtp_port, timeout=5) as smtp:
            if config.smtp_starttls:
                smtp.starttls(context=ssl.create_default_context())
            if config.smtp_username and config.smtp_password:
                smtp.login(config.smtp_username, config.smtp_password.get_secret_value())
            smtp.send_message(message)
    except (OSError, smtplib.SMTPException):
        raise HTTPException(503, "Invitation delivery failed") from None
