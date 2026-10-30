import hashlib
import importlib.util
from datetime import timedelta
from pathlib import Path

import httpx
import pytest
from app.auth import Principal
from app.core.config import settings
from app.document_ocr import OCRSandbox, Suggestions, decrypt, encrypt
from app.documents import PrivateStorage, expire
from app.models import Employee, IdentityDocument, Membership, identifier, now
from app.ocr_worker import analyze, run_once
from conftest import DEV, HR, ORG_A, ORG_B, OWNER, headers, login
from cryptography.fernet import Fernet
from fastapi import HTTPException
from pydantic import SecretStr
from sqlalchemy.orm import sessionmaker


@pytest.fixture
def configured(monkeypatch, db):
    monkeypatch.setattr(settings(), "document_ocr_enabled", True)
    monkeypatch.setattr(settings(), "document_ocr_key", SecretStr(Fernet.generate_key().decode()))
    monkeypatch.setattr(
        "app.ocr_worker.SessionFactory", sessionmaker(db.get_bind(), expire_on_commit=False)
    )


def document(db, **kwargs):
    employee = Employee(
        id=identifier(),
        organization_id=ORG_A,
        user_id=DEV,
        name="Fixture",
        department="Engineering",
    )
    db.add(employee)
    db.flush()
    doc_id = identifier()
    record = IdentityDocument(
        id=doc_id,
        organization_id=ORG_A,
        employee_id=employee.id,
        storage_key=f"{ORG_A}/{employee.id}/{doc_id}",
        media_type="image/png",
        digest="0" * 64,
        expires_at=now() + timedelta(days=1),
        ocr_status="queued",
        **kwargs,
    )
    db.add(record)
    db.commit()
    return record


def suggestions():
    return Suggestions(
        suggested_name="Synthetic Tester", suggested_employee_id="MESH-42", engine="fixture"
    )


def test_encrypted_result_binds_tenant_document_and_remains_hr_only(client, db, configured):
    record = document(db)
    record.ocr_ciphertext = encrypt(record, suggestions())
    record.ocr_status = "completed"
    db.commit()
    assert "Synthetic" not in record.ocr_ciphertext
    route = f"/api/v1/hr/identity-documents/{record.id}/ocr"
    for actor in (DEV, OWNER):
        login(actor)
        assert client.get(route, headers=headers()).status_code == 403
    login(HR)
    assert client.get(route, headers=headers(ORG_B)).status_code == 404
    assert client.get(route, headers=headers()).json()["untrusted"] is True
    record.id = identifier()
    with pytest.raises(HTTPException) as error:
        decrypt(record)
    assert error.value.status_code == 503
    db.rollback()


@pytest.mark.parametrize("change", ["none", "membership", "employee", "manual", "expiry", "lease"])
def test_worker_fences_late_results_without_approving_employee(db, configured, change):
    record = document(db)
    factory = sessionmaker(db.get_bind(), expire_on_commit=False)

    def runner(key, digest):
        assert key == record.storage_key and digest == record.digest
        with factory.begin() as session:
            row = session.get(IdentityDocument, record.id)
            if change == "membership":
                session.get(Membership, (ORG_A, DEV)).active = False
            elif change == "employee":
                session.get(Employee, row.employee_id).status = "offboarded"
            elif change == "manual":
                row.ocr_status, row.ocr_lease_until = "manual_review", None
            elif change == "expiry":
                row.expires_at = now() - timedelta(seconds=1)
            elif change == "lease":
                row.ocr_lease_until = now() + timedelta(minutes=5)
        return suggestions()

    assert not run_once(ORG_B, runner)
    assert run_once(ORG_A, runner)
    db.expire_all()
    current = db.get(IdentityDocument, record.id)
    assert (current.ocr_ciphertext is not None) == (change == "none")
    assert db.get(Employee, current.employee_id).verification_status == "pending"
    if change == "none":
        assert (
            current.ocr_status == "completed"
            and decrypt(current).suggested_employee_id == "MESH-42"
        )


def test_manual_review_cancels_work_and_permits_explicit_human_decision(client, db, configured):
    record = document(db)
    login(HR)
    base = f"/api/v1/hr/identity-documents/{record.id}"
    assert (
        client.post(
            base + "/decision", headers=headers(), json={"decision": "approved"}
        ).status_code
        == 409
    )
    response = client.post(base + "/ocr/manual-review", headers=headers())
    assert response.status_code == 200, response.text
    assert response.json()["ocr_status"] == "manual_review"
    assert (
        client.post(
            base + "/decision", headers=headers(), json={"decision": "approved"}
        ).status_code
        == 200
    )
    assert client.post(base + "/ocr/retry", headers=headers()).status_code == 409


def test_bounded_retries_and_crash_recovery(db, configured):
    record = document(db)
    called = []

    def fail(*_):
        called.append(True)
        raise RuntimeError("PRIVATE TEXT MUST NOT PERSIST")

    for attempt in range(3):
        assert run_once(ORG_A, fail)
        db.expire_all()
        current = db.get(IdentityDocument, record.id)
        assert current.ocr_attempts == attempt + 1
        assert current.ocr_error_code == "ocr_unavailable_or_invalid"
        if attempt < 2:
            assert not run_once(ORG_A, fail)
            current.ocr_lease_until = now() - timedelta(seconds=1)
            db.commit()
    assert current.ocr_status == "failed" and len(called) == 3
    current.ocr_status, current.ocr_lease_until = "running", now() - timedelta(seconds=1)
    db.commit()
    assert run_once(ORG_A, fail) and len(called) == 3


def test_expiry_erases_encrypted_suggestions(db, configured, monkeypatch):
    record = document(db)
    record.ocr_ciphertext = encrypt(record, suggestions())
    record.expires_at = now() - timedelta(seconds=1)
    db.commit()
    monkeypatch.setattr("app.documents.PrivateStorage.delete", lambda *_: None)
    assert expire(db, Principal(HR, ORG_A, "hr")) == 1
    assert record.ocr_ciphertext is None and record.ocr_status == "cancelled"


def test_private_download_is_bounded_canonical_and_opaque_key_uses_apikey(monkeypatch):
    monkeypatch.setattr(settings(), "supabase_url", "https://fixture.supabase.co")
    monkeypatch.setattr(settings(), "supabase_storage_key", SecretStr("sb_secret_fixture"))
    key = f"{ORG_A}/{identifier()}/{identifier()}"

    def handler(request):
        assert (
            "authorization" not in request.headers
            and request.headers["apikey"] == "sb_secret_fixture"
        )
        assert request.url.path.endswith(key)
        return httpx.Response(200, content=b"image")

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        storage = PrivateStorage(client)
        assert storage.download(key) == b"image"
        with pytest.raises(HTTPException):
            storage.download("../escape")
    with httpx.Client(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, content=b"x" * 2097153))
    ) as client:
        with pytest.raises(HTTPException):
            PrivateStorage(client).download(key)


def test_integrity_mismatch_never_invokes_ocr(monkeypatch):
    monkeypatch.setattr("app.ocr_worker.PrivateStorage.download", lambda *_: b"tampered")
    with pytest.raises(ValueError):
        analyze("unused", hashlib.sha256(b"original").hexdigest())


def test_sandbox_has_no_network_mount_key_or_persistent_logs():
    command = OCRSandbox().command("mesh-scan-fixture", "stdin", "ocr")
    for required in (
        "--network=none",
        "--read-only",
        "--log-driver=none",
        "--cap-drop=ALL",
        "--security-opt=no-new-privileges",
        "--memory=512m",
        "--memory-swap=512m",
    ):
        assert required in command
    assert "--mount" not in command and "--volume" not in command
    assert not any("SECRET" in value or "KEY=" in value for value in command)


def test_parser_only_labels_and_conflicting_values_become_unknown():
    path = Path(__file__).resolve().parents[2] / "security-engine/ocr.py"
    spec = importlib.util.spec_from_file_location("ocr_fixture", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    result = module.extract(
        "Name: Synthetic Tester\nEmployee ID: MESH-42\nPassport: SECRET\nAddress: SECRET"
    )
    assert (
        result["suggested_name"] == "Synthetic Tester"
        and result["suggested_employee_id"] == "MESH-42"
    )
    assert "SECRET" not in str(result)
    assert (
        module.extract("Name: One Person\nName: Other Person\nID: 123456789")["suggested_name"]
        is None
    )
    assert module.extract("ID: 123456789")["suggested_employee_id"] is None
