"""Trusted tenant-bound host worker; only image bytes cross the isolated OCR boundary."""

import argparse
import hashlib
from datetime import timedelta
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import or_, select

from app.auth import Principal
from app.core.config import settings
from app.core.db import SessionFactory, assert_runtime_role, tenant_context
from app.core.time import as_utc
from app.document_ocr import OCRSandbox, Suggestions, cipher, encrypt
from app.documents import PrivateStorage, document_key
from app.models import Employee, IdentityDocument, Membership, now
from app.services import emit, lock_tenant


def eligible(db, org, document):
    employee = db.scalar(
        select(Employee)
        .where(
            Employee.organization_id == document.organization_id,
            Employee.id == document.employee_id,
        )
        .with_for_update()
    )
    member = db.get(Membership, (document.organization_id, employee.user_id)) if employee else None
    valid = (
        org is not None
        and org.status == "active"
        and employee is not None
        and employee.status in {"onboarding", "active"}
        and member is not None
        and member.active
        and document.status == "pending_hr"
        and as_utc(document.expires_at) > now()
    )
    return (
        Principal(member.user_id, document.organization_id, member.role)
        if valid and member
        else None
    )


def analyze(key: str, digest: str) -> Suggestions:
    content = PrivateStorage().download(key)
    if hashlib.sha256(content).hexdigest() != digest:
        raise ValueError("Private image integrity check failed")
    return OCRSandbox().analyze(content)


def run_once(organization_id: str, runner=analyze) -> bool:
    if not settings().document_ocr_enabled:
        return False
    cipher()  # Fail before claiming work if the operator key is missing/invalid.
    with SessionFactory.begin() as db:
        assert_runtime_role(db)
        tenant_context(db, organization_id, "ocr-worker")
        org = lock_tenant(db, organization_id)
        record = db.scalar(
            select(IdentityDocument)
            .where(
                IdentityDocument.organization_id == organization_id,
                IdentityDocument.ocr_status.in_(["queued", "running"]),
                or_(
                    IdentityDocument.ocr_lease_until.is_(None),
                    IdentityDocument.ocr_lease_until <= now(),
                ),
            )
            .order_by(IdentityDocument.created_at)
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        if record is None:
            return False
        actor = eligible(db, org, record)
        if actor is None:
            record.ocr_status, record.ocr_lease_until, record.ocr_ciphertext = (
                "cancelled",
                None,
                None,
            )
            return True
        try:
            key = document_key(record, organization_id)
        except HTTPException:
            record.ocr_status, record.ocr_lease_until = "failed", None
            record.ocr_error_code = "invalid_private_reference"
            return True
        if record.ocr_attempts >= 3:
            record.ocr_status, record.ocr_lease_until = "failed", None
            record.ocr_error_code = "attempts_exhausted"
            return True
        record.ocr_attempts += 1
        record.ocr_status, record.ocr_lease_until = "running", now() + timedelta(minutes=3)
        document_id, lease, key, digest = (
            record.id,
            record.ocr_lease_until,
            key,
            record.digest,
        )
    try:
        result = Suggestions.model_validate(runner(key, digest))
        if result.untrusted is not True:
            raise ValueError("Trusted OCR result forbidden")
    except Exception:
        result = None  # Never retain native/provider diagnostics containing document data.
    with SessionFactory.begin() as db:
        assert_runtime_role(db)
        tenant_context(db, organization_id, "ocr-worker")
        org = lock_tenant(db, organization_id)
        record = db.scalar(
            select(IdentityDocument)
            .where(
                IdentityDocument.organization_id == organization_id,
                IdentityDocument.id == document_id,
            )
            .with_for_update()
        )
        if (
            record is None
            or record.ocr_status != "running"
            or record.ocr_lease_until is None
            or as_utc(record.ocr_lease_until) != lease
        ):
            return True
        actor = eligible(db, org, record)
        record.ocr_lease_until = None
        try:
            if document_key(record, organization_id) != key or record.digest != digest:
                raise HTTPException(503, "Invalid private object reference")
        except HTTPException:
            record.ocr_status, record.ocr_error_code = "failed", "invalid_private_reference"
            return True
        if actor is None:
            record.ocr_status, record.ocr_ciphertext = "cancelled", None
            return True
        if result is None:
            record.ocr_status = "failed" if record.ocr_attempts >= 3 else "queued"
            record.ocr_error_code = "ocr_unavailable_or_invalid"
            if record.ocr_status == "queued":
                record.ocr_lease_until = now() + timedelta(seconds=2**record.ocr_attempts)
            emit(db, actor, "employee.document.ocr_failed", record.id)
        else:
            record.ocr_ciphertext = encrypt(record, result)
            record.ocr_status, record.ocr_error_code = "completed", None
            record.ocr_completed_at = now()
            emit(db, actor, "employee.document.ocr_completed", record.id)
    return True


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--organization", required=True, type=UUID)
    parser.add_argument("--loop", action="store_true")
    args = parser.parse_args()
    from app.worker_health import run_loop

    run_loop(
        "ocr",
        str(args.organization),
        lambda: run_once(str(args.organization)),
        repeat=args.loop,
        interval=5,
        idle_only=True,
    )
