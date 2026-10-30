import pytest
from app.core.config import settings
from app.models import Membership, Organization, identifier
from conftest import DEV, ORG_A, ORG_B, OWNER, headers, login

PATH = "/api/v1/users/me/organizations"


def test_memberships_are_discoverable_without_organization_header(client):
    response = client.get(PATH)
    assert response.status_code == 200
    result = response.json()
    assert {row["organization_id"] for row in result["items"]} == {ORG_A, ORG_B}
    assert all(
        set(row) == {"organization_id", "name", "role", "verification_status"}
        for row in result["items"]
    )
    assert result["next_cursor"] is None


def test_self_identity_cannot_be_replaced_by_headers(client, db):
    login(identifier())
    response = client.get(PATH, headers={**headers(), "X-User-ID": OWNER, "X-Role": "owner"})
    assert response.status_code == 200 and response.json()["items"] == []


def test_inactive_membership_and_suspended_organization_are_hidden(client, db):
    db.get(Membership, (ORG_A, OWNER)).active = False
    db.get(Organization, ORG_B).status = "suspended"
    db.commit()
    assert client.get(PATH).json()["items"] == []


def test_cursor_pagination_is_stable_and_nonduplicating(client):
    first = client.get(PATH, params={"limit": 1}).json()
    assert len(first["items"]) == 1 and first["next_cursor"] == ORG_A
    second = client.get(PATH, params={"limit": 1, "cursor": first["next_cursor"]}).json()
    assert [r["organization_id"] for r in second["items"]] == [ORG_B]
    assert second["next_cursor"] is None


def test_empty_filtered_page_still_has_progress_cursor(client, db):
    db.get(Organization, ORG_A).status = "suspended"
    db.commit()
    first = client.get(PATH, params={"limit": 1}).json()
    assert first["items"] == [] and first["next_cursor"] == ORG_A
    second = client.get(PATH, params={"limit": 1, "cursor": first["next_cursor"]}).json()
    assert second["items"][0]["organization_id"] == ORG_B


@pytest.mark.parametrize("query", [{"limit": 0}, {"limit": 101}, {"cursor": "not-a-uuid"}])
def test_discovery_parameters_are_bounded(client, query):
    assert client.get(PATH, params=query).status_code == 422


def test_discovery_does_not_bypass_privileged_mfa(client, monkeypatch):
    monkeypatch.setattr(settings(), "require_privileged_mfa", True)
    assert client.get(PATH).status_code == 200
    assert client.get("/api/v1/users/me", headers=headers()).status_code == 403


def test_roles_are_current_and_do_not_change_access(client, db):
    login(DEV)
    result = client.get(PATH).json()
    assert all(row["role"] == "junior_developer" for row in result["items"])
    assert client.get("/api/v1/employees", headers=headers()).status_code == 403
    db.get(Membership, (ORG_A, DEV)).active = False
    db.commit()
    assert [r["organization_id"] for r in client.get(PATH).json()["items"]] == [ORG_B]
