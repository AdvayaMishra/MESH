from datetime import timedelta
from uuid import UUID

import pytest
from app import document_api
from app.auth import Principal
from app.document_authority import authority
from app.documents import store
from app.enterprise_schemas import Decision
from app.models import Employee, IdentitySession, Membership, Organization, identifier, now
from conftest import DEV, HR, ORG_A
from fastapi import HTTPException
from sqlalchemy.orm import Session
from test_documents_mail import image


@pytest.mark.parametrize(
    "operation",
    ["signed_url", "review", "ocr_result", "retry_ocr", "manual_ocr", "expire_documents"],
)
@pytest.mark.parametrize("change", ["inactive", "demoted", "suspended"])
def test_every_hr_document_operation_rechecks_stale_authority(db, operation, change):
    actor = Principal(HR, ORG_A, "hr")
    member = db.get(Membership, (ORG_A, HR))
    if change == "inactive":
        member.active = False
    elif change == "demoted":
        member.role = "junior_developer"
    else:
        db.get(Organization, ORG_A).status = "suspended"
    db.commit()
    arguments = {"db": db, "p": actor}
    if operation != "expire_documents":
        arguments["document_id"] = UUID(identifier())
    if operation == "review":
        arguments["data"] = Decision(decision="approved")
    with pytest.raises(HTTPException) as error:
        getattr(document_api, operation)(**arguments)
    assert error.value.status_code == 403


@pytest.mark.parametrize(
    "change", ["membership", "organization", "employee", "ownership", "cutoff"]
)
def test_upload_rechecks_access_after_scanning_before_storage(db, monkeypatch, change):
    employee = Employee(organization_id=ORG_A, user_id=DEV, name="Synthetic", department="Test")
    db.add(employee)
    db.commit()
    employee_id = employee.id
    # Seed cached rows to ensure the post-scan checks refresh them.
    db.get(Organization, ORG_A)
    db.get(Membership, (ORG_A, DEV))

    def scan(_):
        with Session(db.get_bind()) as other:
            if change == "membership":
                other.get(Membership, (ORG_A, DEV)).active = False
            elif change == "organization":
                other.get(Organization, ORG_A).status = "suspended"
            elif change == "employee":
                other.get(Employee, employee_id).status = "offboarded"
            elif change == "ownership":
                other.get(Employee, employee_id).user_id = HR
            else:
                other.get(Membership, (ORG_A, DEV)).access_not_before = now()
            other.commit()

    monkeypatch.setattr("app.documents.malware_gate", scan)
    monkeypatch.setattr(
        "app.documents.PrivateStorage.upload",
        lambda *_: pytest.fail("Revoked upload reached Storage"),
    )
    with pytest.raises(HTTPException) as error:
        store(db, Principal(DEV, ORG_A, "junior_developer"), employee_id, "image/png", image())
    assert error.value.status_code == (401 if change == "cutoff" else 403)


@pytest.mark.parametrize("change", ["revoked", "expired", "token_expired"])
def test_fresh_session_check_denies_stale_privileged_content_access(db, change):
    sid = identifier()
    row = IdentitySession(
        user_id=HR,
        provider_session_id=sid,
        client_hint="Synthetic",
        ip_digest="0" * 64,
        expires_at=now() + timedelta(hours=1),
    )
    db.add(row)
    db.commit()
    actor = Principal(HR, ORG_A, "hr", sid, "aal2", now() + timedelta(hours=1), now())
    if change == "token_expired":
        actor = Principal(HR, ORG_A, "hr", sid, "aal2", now() - timedelta(seconds=1), now())
    else:
        with Session(db.get_bind()) as other:
            current = other.get(IdentitySession, row.id)
            if change == "revoked":
                current.revoked_at = now()
            else:
                current.expires_at = now() - timedelta(seconds=1)
            other.commit()
    with pytest.raises(HTTPException) as error:
        authority(db, actor)
    assert error.value.status_code == 401
