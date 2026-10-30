import pytest
from app.core.config import SCIMBinding, settings
from app.lifecycle_integrations import SCIMClient
from app.models import IntegrationAccount, LifecyclePlan, Membership, identifier
from app.worker import consume
from conftest import DEV, ORG_A, headers
from test_lifecycle_compensation import approve, employee, propose
from test_scim_lifecycle import configure, prepare_offboarding


@pytest.mark.parametrize(
    "change", ["external_id", "email", "authority", "added_account", "deleted_account"]
)
def test_execution_requires_the_exact_reviewed_external_inventory(client, db, monkeypatch, change):
    configure(monkeypatch)
    record = employee(db)
    account = IntegrationAccount(
        id=identifier(),
        organization_id=ORG_A,
        user_id=DEV,
        provider="scim",
        external_id="reviewed-user",
    )
    db.add(account)
    db.commit()
    plan = propose(client, record, kind="offboarding", department=None)
    approve(client, plan)
    if change == "external_id":
        account.external_id = "different-user"
    elif change == "email":
        db.get(Membership, (ORG_A, DEV)).email = "changed@example.invalid"
    elif change == "authority":
        monkeypatch.setattr(
            settings(),
            "scim_bindings",
            {
                ORG_A: SCIMBinding(
                    base_url="https://changed.example.invalid/v2", token="rotated-fixture-key"
                )
            },
        )
    elif change == "added_account":
        db.add(
            IntegrationAccount(
                organization_id=ORG_A,
                user_id=DEV,
                provider="manual",
                external_id="new-unreviewed-user",
            )
        )
    else:
        db.delete(account)
    db.commit()
    response = client.post(f"/api/v1/hr/lifecycle/{plan}/execute", headers=headers())
    assert response.status_code == 409
    assert db.get(Membership, (ORG_A, DEV)).active


@pytest.mark.parametrize("change", ["external_id", "email", "authority", "legacy_missing_review"])
def test_worker_never_mutates_an_external_identity_outside_the_reviewed_binding(
    client, db, monkeypatch, change
):
    plan = prepare_offboarding(client, db, monkeypatch)
    account = db.query(IntegrationAccount).filter_by(organization_id=ORG_A, user_id=DEV).one()
    if change == "external_id":
        account.external_id = "different-user"
    elif change == "email":
        db.get(Membership, (ORG_A, DEV)).email = "changed@example.invalid"
    elif change == "authority":
        monkeypatch.setattr(
            settings(),
            "scim_bindings",
            {
                ORG_A: SCIMBinding(
                    base_url="https://changed.example.invalid/v2", token="rotated-fixture-key"
                )
            },
        )
    else:
        record = db.get(LifecyclePlan, plan)
        record.proposed = {
            **record.proposed,
            "integrations": [
                {key: value for key, value in step.items() if key != "review_digest"}
                for step in record.proposed["integrations"]
            ],
        }
    db.commit()
    calls = []
    monkeypatch.setattr(SCIMClient, "revoke", lambda *args: calls.append(True))
    consume(db, ORG_A)
    db.commit()
    assert calls == []
    assert not db.get(Membership, (ORG_A, DEV)).active
    assert db.get(LifecyclePlan, plan).status == "reconciliation_required"


def test_credential_rotation_does_not_change_reviewed_authority(client, db, monkeypatch):
    plan = prepare_offboarding(client, db, monkeypatch)
    monkeypatch.setattr(
        settings(),
        "scim_bindings",
        {ORG_A: SCIMBinding(base_url="https://scim.example.org/v2", token="rotated-fixture-key")},
    )
    calls = []
    monkeypatch.setattr(SCIMClient, "revoke", lambda *args: calls.append(True))
    consume(db, ORG_A)
    db.commit()
    assert calls == [True] and db.get(LifecyclePlan, plan).status == "completed"
