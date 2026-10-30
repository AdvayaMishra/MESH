import io
import json

import pytest
from app.core.config import settings
from app.documents import validate_image
from app.models import Employee, Outbox, identifier
from app.worker import consume
from conftest import DEV, HR, ORG_A, ORG_B, OWNER, headers, login
from cryptography.fernet import Fernet
from fastapi import HTTPException
from PIL import Image
from pydantic import SecretStr
from sqlalchemy import select


def image():
    output = io.BytesIO()
    Image.new("RGB", (8, 8), "white").save(output, "PNG")
    return output.getvalue()


def test_image_validation_rejects_spoofing():
    validate_image(image(), "image/png")
    with pytest.raises(HTTPException):
        validate_image(b"executable-not-image", "image/png")
    with pytest.raises(HTTPException):
        validate_image(b"%PDF-1.0", "application/pdf")


def test_private_upload_requires_malware_and_human_review(client, db, monkeypatch):
    employee = Employee(
        id=identifier(),
        organization_id=ORG_A,
        user_id=DEV,
        name="Employee",
        department="Engineering",
    )
    db.add(employee)
    db.commit()
    login(DEV)
    route = f"/api/v1/employees/{employee.id}/identity-documents"
    assert (
        client.post(
            route, headers={**headers(), "Content-Type": "image/png"}, content=image()
        ).status_code
        == 503
    )
    monkeypatch.setattr("app.documents.malware_gate", lambda _: None)
    monkeypatch.setattr("app.documents.PrivateStorage.upload", lambda *a: None)
    uploaded = client.post(
        route, headers={**headers(), "Content-Type": "image/png"}, content=image()
    )
    assert uploaded.status_code == 201, uploaded.text
    document = uploaded.json()["id"]
    assert db.get(Employee, employee.id).verification_status == "pending"
    login(OWNER)
    assert (
        client.get(
            f"/api/v1/hr/identity-documents/{document}/signed-url", headers=headers()
        ).status_code
        == 403
    )
    login(HR)
    assert (
        client.get(
            f"/api/v1/hr/identity-documents/{document}/signed-url", headers=headers(ORG_B)
        ).status_code
        == 404
    )
    reviewed = client.post(
        f"/api/v1/hr/identity-documents/{document}/decision",
        headers=headers(),
        json={"decision": "approved"},
    )
    assert reviewed.status_code == 200, reviewed.text
    assert db.get(Employee, employee.id).verification_status == "approved"


def test_invitation_durable_ciphertext_and_worker_delivery(client, db, monkeypatch):
    key = Fernet.generate_key().decode()
    monkeypatch.setattr(settings(), "smtp_host", "local-test-mail")
    monkeypatch.setattr(settings(), "mail_encryption_key", SecretStr(key))
    response = client.post(
        "/api/v1/invitations", headers=headers(), json={"email": "new@example.org", "role": "hr"}
    )
    assert response.status_code == 201, response.text
    mail = db.scalar(select(Outbox).where(Outbox.topic == "mail.invitation"))
    assert "new@example.org" not in json.dumps(mail.payload)
    decrypted = json.loads(Fernet(key.encode()).decrypt(mail.payload["ciphertext"].encode()))
    delivered = []
    monkeypatch.setattr(
        "app.worker.send_invitation",
        lambda email, token, org: delivered.append((email, token, org)),
    )
    consume(db, ORG_A)
    db.commit()
    assert delivered == [("new@example.org", decrypted["token"], ORG_A)]
    assert "ciphertext" not in mail.payload
    assert consume(db, ORG_A) == 0


def test_mail_only_worker_leaves_non_mail_integrations_pending(client, db, monkeypatch):
    monkeypatch.setattr(settings(), "smtp_host", "local-test-mail")
    monkeypatch.setattr(
        settings(), "mail_encryption_key", SecretStr(Fernet.generate_key().decode())
    )
    response = client.post(
        "/api/v1/invitations",
        headers=headers(),
        json={"email": "mail-only@example.org", "role": "hr"},
    )
    assert response.status_code == 201
    unrelated = Outbox(
        organization_id=ORG_A,
        topic="lifecycle.scim.revoke",
        payload={"target_id": "not-for-mail-worker"},
    )
    db.add(unrelated)
    db.commit()
    sent = []
    monkeypatch.setattr("app.worker.send_invitation", lambda *args: sent.append(args))
    monkeypatch.setattr(
        "app.lifecycle_integrations.revoke_scim",
        lambda *args: pytest.fail("Mail-only worker invoked SCIM"),
    )
    assert consume(db, ORG_A, mail_only=True) == 1
    db.commit()
    assert len(sent) == 1
    assert unrelated.status == "pending"
    assert consume(db, ORG_A, mail_only=True) == 0
