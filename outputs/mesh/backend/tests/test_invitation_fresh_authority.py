from datetime import timedelta, timezone

import pytest
from app.auth import Identity, Principal
from app.core.config import settings
from app.models import Invitation, Membership, Organization, Outbox, identifier, now
from app.services import accept_invitation, invitation
from app.worker import consume
from conftest import HR, ORG_A, OWNER, headers, login
from cryptography.fernet import Fernet
from fastapi import HTTPException
from pydantic import SecretStr
from sqlalchemy import select


@pytest.mark.parametrize("change", ["inactive", "role", "organization"])
def test_cached_inviter_cannot_create_after_revocation(db, change):
    actor = Principal(OWNER, ORG_A, "owner")
    if change == "inactive":
        db.get(Membership, (ORG_A, OWNER)).active = False
    elif change == "role":
        db.get(Membership, (ORG_A, OWNER)).role = "junior_developer"
    else:
        db.get(Organization, ORG_A).status = "suspended"
    db.commit()
    with pytest.raises(HTTPException) as error:
        invitation(db, actor, "new@example.invalid", "hr")
    assert error.value.status_code == 403
    assert db.scalar(select(Invitation.id)) is None


@pytest.mark.parametrize("issuer_change", ["inactive", "role", "deleted"])
def test_old_link_cannot_grant_access_after_issuer_loses_authority(db, issuer_change):
    record, token = invitation(db, Principal(OWNER, ORG_A, "owner"), "new@example.invalid", "hr")
    db.commit()
    issuer = db.get(Membership, (ORG_A, OWNER))
    if issuer_change == "inactive":
        issuer.active = False
    elif issuer_change == "role":
        issuer.role = "junior_developer"
    else:
        db.delete(issuer)
    db.commit()
    uid = identifier()
    with pytest.raises(HTTPException) as error:
        accept_invitation(db, Principal(uid, ORG_A, ""), Identity(uid, record.email), token)
    assert error.value.status_code == 400
    assert db.get(Membership, (ORG_A, uid)) is None
    assert db.get(Invitation, record.id).status == "pending"


def test_mail_skips_links_with_revoked_issuer(client, db, monkeypatch):
    monkeypatch.setattr(settings(), "smtp_host", "fixture-mail")
    monkeypatch.setattr(
        settings(), "mail_encryption_key", SecretStr(Fernet.generate_key().decode())
    )
    response = client.post(
        "/api/v1/invitations",
        headers=headers(),
        json={"email": "new@example.invalid", "role": "hr"},
    )
    assert response.status_code == 201
    db.get(Membership, (ORG_A, OWNER)).active = False
    db.commit()
    monkeypatch.setattr(
        "app.worker.send_invitation", lambda *args: pytest.fail("Revoked issuer's link was sent")
    )
    consume(db, ORG_A, mail_only=True)
    db.commit()
    job = db.scalar(select(Outbox).where(Outbox.topic == "mail.invitation"))
    assert job.payload["outcome"] == "skipped_inactive" and "ciphertext" not in job.payload


def test_authorized_resend_replaces_issuer_without_reusing_old_token(client, db, monkeypatch):
    monkeypatch.setattr(settings(), "smtp_host", "fixture-mail")
    monkeypatch.setattr(
        settings(), "mail_encryption_key", SecretStr(Fernet.generate_key().decode())
    )
    response = client.post(
        "/api/v1/invitations",
        headers=headers(),
        json={"email": "new@example.invalid", "role": "hr"},
    )
    reference = response.json()["id"]
    old = db.scalar(select(Outbox).where(Outbox.topic == "mail.invitation"))
    old.created_at = now() - timedelta(minutes=2)
    replacement_owner = identifier()
    db.add(
        Membership(
            organization_id=ORG_A,
            user_id=replacement_owner,
            email="replacement@example.invalid",
            role="owner",
        )
    )
    db.get(Membership, (ORG_A, OWNER)).active = False
    db.commit()
    login(replacement_owner)
    assert (
        client.post(f"/api/v1/invitations/{reference}/resend", headers=headers()).status_code == 202
    )
    assert db.get(Invitation, reference).creator_id == replacement_owner
    sent = []
    monkeypatch.setattr("app.worker.send_invitation", lambda *args: sent.append(args))
    consume(db, ORG_A, mail_only=True)
    db.commit()
    assert len(sent) == 1 and old.payload["outcome"] == "skipped_superseded"


def test_hr_role_change_invalidates_employee_invite(db):
    record, token = invitation(
        db, Principal(HR, ORG_A, "hr"), "new@example.invalid", "security_analyst"
    )
    db.commit()
    db.get(Membership, (ORG_A, HR)).role = "owner"
    db.commit()
    uid = identifier()
    with pytest.raises(HTTPException):
        accept_invitation(db, Principal(uid, ORG_A, ""), Identity(uid, record.email), token)


def test_expired_link_with_non_utc_offset_is_not_extended(db):
    record, token = invitation(
        db, Principal(OWNER, ORG_A, "owner"), "expired@example.invalid", "hr"
    )
    record.expires_at = (now() - timedelta(minutes=1)).astimezone(
        timezone(timedelta(hours=5, minutes=30))
    )
    db.commit()
    uid = identifier()
    with pytest.raises(HTTPException) as error:
        accept_invitation(db, Principal(uid, ORG_A, ""), Identity(uid, record.email), token)
    assert error.value.status_code == 400
    assert db.get(Membership, (ORG_A, uid)) is None
