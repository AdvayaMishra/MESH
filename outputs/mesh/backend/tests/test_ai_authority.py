"""AI context collection and dispatch reject revoked cached authority."""

from uuid import UUID

import pytest
from app.ai import generate
from app.auth import Principal
from app.intelligence_api import hr_ai, owner_ai, project_ai, risk_ai, vader_ai
from app.models import AIUsage, AuditLog, Membership, Organization
from conftest import ANALYST, DEV, HR, ORG_A, OWNER
from fastapi import HTTPException


@pytest.mark.parametrize(
    "handler,user,role,needs_target",
    [
        (owner_ai, OWNER, "owner", False),
        (hr_ai, HR, "hr", False),
        (project_ai, DEV, "junior_developer", True),
        (vader_ai, ANALYST, "security_analyst", True),
        (risk_ai, ANALYST, "security_analyst", True),
    ],
)
@pytest.mark.parametrize("revocation", ["inactive", "role", "organization"])
def test_every_insight_refreshes_authority_before_context(
    db, monkeypatch, handler, user, role, needs_target, revocation
):
    actor = Principal(user, ORG_A, role)
    if revocation == "inactive":
        db.get(Membership, (ORG_A, user)).active = False
    elif revocation == "role":
        db.get(Membership, (ORG_A, user)).role = "hr" if role != "hr" else "junior_developer"
    else:
        db.get(Organization, ORG_A).status = "suspended"
    db.commit()
    calls = []
    monkeypatch.setattr("app.intelligence_api.generate", lambda *args: calls.append(args))
    with pytest.raises(HTTPException) as error:
        if needs_target:
            handler(UUID("99999999-9999-4999-8999-999999999999"), db, actor)
        else:
            handler(db, actor)
    assert error.value.status_code == 403
    assert not calls and db.query(AIUsage).count() == 0 and db.query(AuditLog).count() == 0


def test_direct_generation_rejects_revoked_principal_before_adapter(db):
    actor = Principal(OWNER, ORG_A, "owner")
    db.get(Membership, (ORG_A, OWNER)).active = False
    db.commit()

    class Adapter:
        def generate(self, purpose, context):
            pytest.fail("A revoked actor must never reach a model adapter")

    with pytest.raises(HTTPException) as error:
        generate(db, actor, "owner", {"records": 1}, Adapter())
    assert error.value.status_code == 403


def test_local_owner_insight_still_works_with_current_authority(client):
    response = client.get("/api/v1/ai/owner", headers={"X-Organization-ID": ORG_A})
    assert response.status_code == 200
    assert response.json()["provider"] == "local-deterministic"
