from uuid import UUID

import pytest
from app import account_api
from app.account_api import OrganizationStatus, organization_status
from app.auth import Identity
from app.core.config import settings
from app.models import AuditLog, Membership, Organization, Outbox
from conftest import ORG_A, OWNER
from fastapi import HTTPException


@pytest.mark.parametrize(
    "change", [{"active": False}, {"role": "hr"}, {"role": "junior_developer"}]
)
def test_status_change_refreshes_owner_after_tenant_lock(db, monkeypatch, change):
    original = account_api.lock_tenant

    def revoke_during_wait(session, organization):
        session.execute(
            Membership.__table__.update()
            .where(Membership.organization_id == ORG_A, Membership.user_id == OWNER)
            .values(**change)
        )
        return original(session, organization)

    monkeypatch.setattr(account_api, "lock_tenant", revoke_during_wait)
    with pytest.raises(HTTPException) as error:
        organization_status(
            OrganizationStatus(status="suspended"),
            Identity(OWNER, "fixture@example.org", "aal2"),
            db,
            UUID(ORG_A),
        )
    assert error.value.status_code == 403
    assert db.get(Organization, ORG_A).status == "active"
    assert db.query(AuditLog).count() == 0 and db.query(Outbox).count() == 0


def test_current_owner_can_suspend_and_reactivate_without_losing_audit(db):
    who = Identity(OWNER, "fixture@example.org", "aal2")
    for status in ("suspended", "active"):
        result = organization_status(OrganizationStatus(status=status), who, db, UUID(ORG_A))
        assert result.status == status and db.get(Organization, ORG_A).status == status
    db.flush()
    assert db.query(AuditLog).count() == 2 and db.query(Outbox).count() == 2


def test_privileged_mfa_is_still_required_before_status_change(db, monkeypatch):
    monkeypatch.setattr(settings(), "require_privileged_mfa", True)
    with pytest.raises(HTTPException) as error:
        organization_status(
            OrganizationStatus(status="suspended"),
            Identity(OWNER, "fixture@example.org", "aal1"),
            db,
            UUID(ORG_A),
        )
    assert error.value.status_code == 403 and db.get(Organization, ORG_A).status == "active"


def test_outsider_cannot_probe_unknown_organization_status(db):
    with pytest.raises(HTTPException) as error:
        organization_status(
            OrganizationStatus(status="suspended"),
            Identity(OWNER, "fixture@example.org", "aal2"),
            db,
            UUID("99999999-9999-4999-8999-999999999999"),
        )
    assert error.value.status_code == 403
