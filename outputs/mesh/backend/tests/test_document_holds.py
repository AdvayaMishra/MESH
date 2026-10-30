from datetime import timedelta
from uuid import uuid4

import pytest
from app.auth import Principal
from app.document_holds import HoldInput, place
from app.documents import expire
from app.models import (
    AuditLog,
    Employee,
    IdentityDocument,
    Membership,
    identifier,
    now,
)
from conftest import DEV, HR, ORG_A, ORG_B, OWNER, headers, login
from fastapi import HTTPException
from sqlalchemy import select

HR2 = "ffffffff-ffff-4fff-8fff-ffffffffffff"


@pytest.fixture
def record(db):
    db.add(
        Membership(organization_id=ORG_A, user_id=HR2, email="reviewer@example.invalid", role="hr")
    )
    employee = Employee(organization_id=ORG_A, user_id=DEV, name="Synthetic", department="Test")
    db.add(employee)
    db.flush()
    doc_id = identifier()
    row = IdentityDocument(
        id=doc_id,
        organization_id=ORG_A,
        employee_id=employee.id,
        storage_key=f"{ORG_A}/{employee.id}/{doc_id}",
        media_type="image/png",
        digest="0" * 64,
        expires_at=now() - timedelta(days=1),
        ocr_ciphertext="encrypted-fixture",
    )
    db.add(row)
    db.commit()
    return row


def put(client, row, **kwargs):
    return client.post(
        f"/api/v1/hr/identity-documents/{row.id}/holds",
        headers=headers(),
        json={"request_key": str(uuid4()), "reason_code": "investigation", **kwargs},
    )


def test_hold_preserves_expired_bytes_without_extending_access_then_independent_release(
    client, db, record, monkeypatch
):
    login(HR)
    response = put(client, record)
    assert response.status_code == 201, response.text
    hold = response.json()
    assert "storage_key" not in hold and "ocr_ciphertext" not in hold
    deleted = []
    monkeypatch.setattr("app.documents.PrivateStorage.delete", lambda _, key: deleted.append(key))
    assert expire(db, Principal("retention-worker", ORG_A, "system")) == 0
    assert deleted == [] and record.ocr_ciphertext == "encrypted-fixture"
    for suffix in ("signed-url", "ocr"):
        assert (
            client.get(
                f"/api/v1/hr/identity-documents/{record.id}/{suffix}", headers=headers()
            ).status_code
            == 410
        )
    url = f"/api/v1/hr/identity-document-holds/{hold['id']}/release"
    assert client.post(url, headers=headers(), json={"reason_code": "resolved"}).status_code == 409
    login(HR2)
    response = client.post(url, headers=headers(), json={"reason_code": "resolved"})
    assert response.status_code == 200, response.text
    assert response.json()["released_by"] == HR2
    assert client.post(url, headers=headers(), json={"reason_code": "resolved"}).status_code == 200
    assert client.post(url, headers=headers(), json={"reason_code": "other"}).status_code == 409
    assert expire(db, Principal("retention-worker", ORG_A, "system")) == 1
    assert deleted == [record.storage_key] and record.ocr_ciphertext is None
    assert record.status == "deleted"
    actions = db.scalars(select(AuditLog.action)).all()
    assert actions.count("employee.document.hold_placed") == 1
    assert actions.count("employee.document.hold_released") == 1


def test_replay_is_bound_to_actor_document_reason_and_does_not_reactivate_released_hold(
    client, db, record
):
    login(HR)
    key = str(uuid4())
    first = put(client, record, request_key=key)
    assert first.status_code == 201, first.text
    assert put(client, record, request_key=key).json()["id"] == first.json()["id"]
    assert put(client, record, request_key=key, reason_code="other").status_code == 409
    assert put(client, record).status_code == 409
    login(HR2)
    assert put(client, record, request_key=key).status_code == 409
    assert (
        client.post(
            f"/api/v1/hr/identity-document-holds/{first.json()['id']}/release",
            headers=headers(),
            json={"reason_code": "resolved"},
        ).status_code
        == 200
    )
    login(HR)
    assert put(client, record, request_key=key).json()["released_at"] is not None
    assert put(client, record).status_code == 201


@pytest.mark.parametrize("user", [OWNER, DEV])
def test_hold_is_hr_only(client, record, user):
    login(user)
    assert put(client, record).status_code == 403


def test_cross_tenant_read_release_and_create_are_hidden(client, record):
    login(HR)
    hold = put(client, record).json()
    root = f"/api/v1/hr/identity-documents/{record.id}/holds"
    assert client.get(root, headers=headers(ORG_B)).status_code == 404
    assert (
        client.post(
            root, headers=headers(ORG_B), json={"request_key": str(uuid4()), "reason_code": "other"}
        ).status_code
        == 404
    )
    assert (
        client.post(
            f"/api/v1/hr/identity-document-holds/{hold['id']}/release",
            headers=headers(ORG_B),
            json={"reason_code": "resolved"},
        ).status_code
        == 404
    )


def test_self_preservation_review_and_deleted_document_are_rejected(client, db, record):
    login(HR)
    employee = db.get(Employee, record.employee_id)
    employee.user_id = HR
    db.commit()
    assert put(client, record).status_code == 409
    employee.user_id = DEV
    record.status = "deleted"
    db.commit()
    assert put(client, record).status_code == 410


@pytest.mark.parametrize(
    "payload",
    [{"reason_code": "private free text"}, {"unexpected": "PII"}, {"request_key": "not-a-uuid"}],
)
def test_only_bounded_classification_codes_and_request_keys_are_accepted(client, record, payload):
    login(HR)
    assert put(client, record, **payload).status_code == 422


def test_hold_list_is_bounded_audited_and_has_no_private_document_bytes(client, db, record):
    login(HR)
    put(client, record)
    url = f"/api/v1/hr/identity-documents/{record.id}/holds"
    response = client.get(url, headers=headers(), params={"limit": 1})
    assert response.status_code == 200 and len(response.json()) == 1
    assert "encrypted-fixture" not in response.text and record.storage_key not in response.text
    assert client.get(url, headers=headers(), params={"limit": 0}).status_code == 422
    assert client.get(url, headers=headers(), params={"offset": 1}).json() == []


@pytest.mark.parametrize("change", ["inactive", "demoted", "suspended"])
def test_stale_principal_cannot_place_after_authority_change(db, record, change):
    member = db.get(Membership, (ORG_A, HR))
    if change == "inactive":
        member.active = False
    elif change == "demoted":
        member.role = "junior_developer"
    else:
        from app.models import Organization

        db.get(Organization, ORG_A).status = "suspended"
    db.commit()
    with pytest.raises(HTTPException) as error:
        place(
            db,
            Principal(HR, ORG_A, "hr"),
            record.id,
            HoldInput(request_key=uuid4(), reason_code="other"),
        )
    assert error.value.status_code == 403


def test_retention_is_bounded_and_failed_storage_deletion_preserves_reference(
    db, record, monkeypatch
):
    def unavailable(*_):
        raise HTTPException(503, "fixture unavailable")

    monkeypatch.setattr("app.documents.PrivateStorage.delete", unavailable)
    with pytest.raises(HTTPException):
        expire(db, Principal("retention-worker", ORG_A, "system"))
    assert record.status != "deleted" and record.ocr_ciphertext == "encrypted-fixture"
    for _ in range(51):
        doc_id = identifier()
        db.add(
            IdentityDocument(
                id=doc_id,
                organization_id=ORG_A,
                employee_id=record.employee_id,
                storage_key=f"{ORG_A}/{record.employee_id}/{doc_id}",
                media_type="image/png",
                digest="1" * 64,
                expires_at=now() - timedelta(days=1),
            )
        )
    db.commit()
    deleted = []
    monkeypatch.setattr("app.documents.PrivateStorage.delete", lambda _, key: deleted.append(key))
    assert expire(db, Principal("retention-worker", ORG_A, "system")) == 50
    assert len(deleted) == 50


def test_hold_fences_queued_ocr_and_preserves_existing_encrypted_evidence(
    client, db, record, monkeypatch
):
    from app.core.config import settings
    from cryptography.fernet import Fernet
    from pydantic import SecretStr

    record.expires_at = now() + timedelta(days=1)
    record.ocr_status = "running"
    record.ocr_lease_until = now() + timedelta(minutes=3)
    db.commit()
    login(HR)
    assert put(client, record).status_code == 201
    assert record.ocr_status == "cancelled" and record.ocr_lease_until is None
    assert record.ocr_ciphertext == "encrypted-fixture"
    monkeypatch.setattr(settings(), "document_ocr_enabled", True)
    monkeypatch.setattr(settings(), "document_ocr_key", SecretStr(Fernet.generate_key().decode()))
    for suffix in ("retry", "manual-review"):
        assert (
            client.post(
                f"/api/v1/hr/identity-documents/{record.id}/ocr/{suffix}", headers=headers()
            ).status_code
            == 409
        )
    assert record.ocr_ciphertext == "encrypted-fixture"
