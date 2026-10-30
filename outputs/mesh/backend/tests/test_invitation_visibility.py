from datetime import timedelta

import pytest
from app.core.config import settings
from app.models import Invitation, Outbox, now
from app.worker import consume
from conftest import ANALYST, DEV, HR, ORG_A, ORG_B, OWNER, headers, login
from cryptography.fernet import Fernet
from pydantic import SecretStr
from sqlalchemy import select


def invitation(client, monkeypatch, email="invitation-fixture@example.invalid", role="hr"):
    monkeypatch.setattr(settings(), "smtp_host", "fixture-mail")
    monkeypatch.setattr(
        settings(), "mail_encryption_key", SecretStr(Fernet.generate_key().decode())
    )
    login(OWNER if role == "hr" else HR)
    response = client.post(
        "/api/v1/invitations", headers=headers(), json={"email": email, "role": role}
    )
    assert response.status_code == 201
    return response.json()["id"]


def delivery(client, reference):
    return client.get(f"/api/v1/invitations/{reference}/delivery", headers=headers())


def test_list_is_scoped_paginated_and_omits_tokens(client, db, monkeypatch):
    reference = invitation(client, monkeypatch)
    login(OWNER)
    rows = client.get("/api/v1/invitations?status=pending&limit=1", headers=headers())
    assert rows.status_code == 200 and rows.json()[0]["id"] == reference
    assert "token" not in rows.text and "ciphertext" not in rows.text
    assert client.get("/api/v1/invitations?offset=1", headers=headers()).json() == []
    assert client.get("/api/v1/invitations", headers=headers(ORG_B)).json() == []
    assert (
        client.get(f"/api/v1/invitations/{reference}/delivery", headers=headers(ORG_B)).status_code
        == 404
    )
    assert client.get("/api/v1/invitations?limit=1001", headers=headers()).status_code == 422


@pytest.mark.parametrize("user", [DEV, ANALYST])
def test_employees_cannot_read_invitation_metadata(client, monkeypatch, user):
    reference = invitation(client, monkeypatch)
    login(user)
    assert client.get("/api/v1/invitations", headers=headers()).status_code == 403
    assert delivery(client, reference).status_code == 403


def test_hr_cannot_read_owner_created_hr_invites(client, monkeypatch):
    reference = invitation(client, monkeypatch)
    login(HR)
    assert client.get("/api/v1/invitations", headers=headers()).json() == []
    assert delivery(client, reference).status_code == 403


def test_hr_can_read_employee_invites(client, monkeypatch):
    reference = invitation(client, monkeypatch, role="junior_developer")
    assert client.get("/api/v1/invitations", headers=headers()).json()[0]["id"] == reference
    assert delivery(client, reference).json()["state"] == "queued"


def test_smtp_acceptance_is_distinct_from_inbox_delivery(client, db, monkeypatch):
    reference = invitation(client, monkeypatch)
    sent = []
    monkeypatch.setattr("app.worker.send_invitation", lambda *args: sent.append(args))
    assert delivery(client, reference).json()["state"] == "queued"
    consume(db, ORG_A, mail_only=True)
    db.commit()
    result = delivery(client, reference).json()
    assert len(sent) == 1
    assert result["state"] == "smtp_accepted" and result["outcome"] == "smtp_accepted"
    assert result["processed_at"] and result["inbox_delivery_verified"] is False
    assert "ciphertext" not in str(result) and "token" not in str(result)


@pytest.mark.parametrize(
    "kind,outcome",
    [
        ("revoked", "skipped_inactive"),
        ("expired", "skipped_expired"),
        ("superseded", "skipped_superseded"),
    ],
)
def test_skipped_invites_are_never_reported_as_sent(client, db, monkeypatch, kind, outcome):
    reference = invitation(client, monkeypatch)
    record = db.get(Invitation, reference)
    if kind == "revoked":
        record.status = "revoked"
    elif kind == "expired":
        record.expires_at = now() - timedelta(seconds=1)
    else:
        record.token_hash = "0" * 64
    db.commit()
    monkeypatch.setattr(
        "app.worker.send_invitation", lambda *args: pytest.fail("Skipped invitation sent")
    )
    consume(db, ORG_A, mail_only=True)
    db.commit()
    value = delivery(client, reference).json()
    assert value["state"] == "skipped" and value["outcome"] == outcome


def test_mail_failures_report_retry_and_dead_letter_without_ciphertext(client, db, monkeypatch):
    reference = invitation(client, monkeypatch)

    def fail(*args):
        raise RuntimeError("private-provider-error")

    monkeypatch.setattr("app.worker.send_invitation", fail)
    consume(db, ORG_A, mail_only=True)
    db.commit()
    result = delivery(client, reference)
    assert result.json()["state"] == "retrying" and result.json()["attempts"] == 1
    assert "private-provider-error" not in result.text and "ciphertext" not in result.text
    job = db.scalar(select(Outbox).where(Outbox.topic == "mail.invitation"))
    job.status = "dead_letter"
    db.commit()
    assert delivery(client, reference).json()["state"] == "failed"


def test_legacy_processed_mail_is_not_claimed_smtp_accepted(client, db, monkeypatch):
    reference = invitation(client, monkeypatch)
    job = db.scalar(select(Outbox).where(Outbox.topic == "mail.invitation"))
    job.status = "delivered"
    job.payload = {"invitation_id": reference}
    db.commit()
    assert delivery(client, reference).json()["state"] == "processed_unknown"


def test_no_mail_job_reports_not_queued(client, db, monkeypatch):
    reference = invitation(client, monkeypatch)
    job = db.scalar(select(Outbox).where(Outbox.topic == "mail.invitation"))
    db.delete(job)
    db.commit()
    value = delivery(client, reference).json()
    assert value["state"] == "not_queued" and value["job_id"] is None


def test_resend_status_tracks_latest_message_and_old_token_is_skipped(client, db, monkeypatch):
    reference = invitation(client, monkeypatch)
    old_job = db.scalar(select(Outbox).where(Outbox.topic == "mail.invitation"))
    old_job.created_at = now() - timedelta(minutes=2)
    db.commit()
    assert (
        client.post(f"/api/v1/invitations/{reference}/resend", headers=headers()).status_code == 202
    )
    new_job_id = delivery(client, reference).json()["job_id"]
    assert new_job_id != old_job.id
    sent = []
    monkeypatch.setattr("app.worker.send_invitation", lambda *args: sent.append(args))
    consume(db, ORG_A, mail_only=True)
    db.commit()
    assert len(sent) == 1
    assert old_job.payload["outcome"] == "skipped_superseded"
    assert delivery(client, reference).json()["state"] == "smtp_accepted"
