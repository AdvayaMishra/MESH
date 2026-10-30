from datetime import timedelta

import httpx
import pytest
from app.auth import Principal
from app.core.config import settings
from app.documents import PrivateStorage, expire
from app.models import Employee, IdentityDocument, identifier, now
from app.ocr_worker import run_once
from conftest import DEV, HR, ORG_A, ORG_B, OWNER, headers, login
from cryptography.fernet import Fernet
from fastapi import HTTPException
from pydantic import SecretStr
from sqlalchemy.orm import sessionmaker


@pytest.fixture
def bound(db):
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
        expires_at=now() + timedelta(days=1),
        ocr_status="queued",
    )
    db.add(row)
    db.commit()
    return row


@pytest.mark.parametrize("method", ["upload", "download", "sign", "delete"])
@pytest.mark.parametrize("key", ["../escape", "a/b/c", None, f"{ORG_A}/{DEV}/{HR}?token=bad"])
def test_all_storage_object_operations_reject_invalid_keys_before_provider(method, key):
    with httpx.Client(
        transport=httpx.MockTransport(lambda _: pytest.fail("Invalid key reached provider"))
    ) as client:
        args = (key, b"fixture", "image/png") if method == "upload" else (key,)
        with pytest.raises(HTTPException) as error:
            getattr(PrivateStorage(client), method)(*args)
    assert error.value.status_code == 503


@pytest.mark.parametrize("component", ["organization", "employee", "document"])
def test_mismatched_persisted_reference_cannot_sign_or_expire_another_object(
    client, db, bound, monkeypatch, component
):
    parts = bound.storage_key.split("/")
    parts[{"organization": 0, "employee": 1, "document": 2}[component]] = (
        ORG_B if component == "organization" else identifier()
    )
    bound.storage_key = "/".join(parts)
    db.commit()
    monkeypatch.setattr(
        "app.documents.PrivateStorage.sign", lambda *_: pytest.fail("Mismatched object signed")
    )
    monkeypatch.setattr(
        "app.documents.PrivateStorage.delete", lambda *_: pytest.fail("Mismatched object deleted")
    )
    login(HR)
    response = client.get(f"/api/v1/hr/identity-documents/{bound.id}/signed-url", headers=headers())
    assert response.status_code == 503
    assert bound.storage_key not in response.text
    bound.expires_at = now() - timedelta(days=1)
    db.commit()
    with pytest.raises(HTTPException) as error:
        expire(db, Principal("retention-worker", ORG_A, "system"))
    assert error.value.status_code == 503 and bound.status != "deleted"


@pytest.mark.parametrize("during_processing", [False, True])
def test_ocr_rejects_reference_mismatch_before_call_or_publication(
    db, bound, monkeypatch, during_processing
):
    from app.document_ocr import Suggestions

    factory = sessionmaker(db.get_bind(), expire_on_commit=False)
    monkeypatch.setattr("app.ocr_worker.SessionFactory", factory)
    monkeypatch.setattr(settings(), "document_ocr_enabled", True)
    monkeypatch.setattr(settings(), "document_ocr_key", SecretStr(Fernet.generate_key().decode()))

    def corrupt(row):
        row.storage_key = f"{ORG_B}/{row.employee_id}/{row.id}"

    if not during_processing:
        corrupt(bound)
        db.commit()
    calls = []

    def runner(*_):
        calls.append(True)
        with factory.begin() as current:
            corrupt(current.get(IdentityDocument, bound.id))
        return Suggestions(suggested_name="Synthetic", engine="fixture")

    assert run_once(ORG_A, runner)
    db.expire_all()
    assert calls == ([True] if during_processing else [])
    current = db.get(IdentityDocument, bound.id)
    assert current.ocr_status == "failed" and current.ocr_error_code == "invalid_private_reference"
    assert current.ocr_ciphertext is None


def test_hr_review_queue_filters_pages_and_never_returns_document_secrets(client, db, bound):
    from app.models import DocumentHold

    db.add(
        DocumentHold(
            organization_id=ORG_A,
            document_id=bound.id,
            request_key=identifier(),
            reason_code="other",
            placed_by=HR,
        )
    )
    ids = []
    for status, expired in (("pending_hr", False), ("pending_hr", True), ("approved", False)):
        doc_id = identifier()
        ids.append(doc_id)
        db.add(
            IdentityDocument(
                id=doc_id,
                organization_id=ORG_A,
                employee_id=bound.employee_id,
                storage_key=f"{ORG_A}/{bound.employee_id}/{doc_id}",
                media_type="image/png",
                digest="1" * 64,
                status=status,
                expires_at=now() + timedelta(days=-1 if expired else 1),
                ocr_ciphertext="PRIVATE_OCR",
            )
        )
    db.commit()
    login(HR)
    route = "/api/v1/hr/identity-documents"
    response = client.get(route, headers=headers())
    assert response.status_code == 200, response.text
    assert {row["id"] for row in response.json()["items"]} == {bound.id, ids[0]}
    assert (
        next(row for row in response.json()["items"] if row["id"] == bound.id)["active_hold"]
        is True
    )
    assert bound.storage_key not in response.text and "PRIVATE_OCR" not in response.text
    assert "digest" not in response.text and "storage_key" not in response.text
    first = client.get(route, headers=headers(), params={"limit": 1}).json()
    second = client.get(route, headers=headers(), params={"limit": 1, "offset": 1}).json()
    assert first["has_more"] and not second["has_more"]
    assert first["items"][0]["id"] != second["items"][0]["id"]
    assert (
        len(
            client.get(
                route, headers=headers(), params={"status": "all", "include_expired": True}
            ).json()["items"]
        )
        == 4
    )
    approved = client.get(
        route, headers=headers(), params={"status": "approved", "employee_id": bound.employee_id}
    ).json()
    assert [row["id"] for row in approved["items"]] == [ids[2]]
    assert client.get(route, headers=headers(ORG_B)).json()["items"] == []
    assert (
        client.get(
            route, headers=headers(ORG_B), params={"employee_id": bound.employee_id}
        ).status_code
        == 404
    )
    login(OWNER)
    assert client.get(route, headers=headers()).status_code == 403


@pytest.mark.parametrize(
    "params", [{"status": "arbitrary"}, {"limit": 0}, {"offset": -1}, {"employee_id": "invalid"}]
)
def test_hr_review_queue_rejects_invalid_filters(client, bound, params):
    login(HR)
    assert (
        client.get("/api/v1/hr/identity-documents", headers=headers(), params=params).status_code
        == 422
    )
