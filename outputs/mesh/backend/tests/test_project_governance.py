from app.auth import Principal
from app.models import Membership, Project, identifier
from app.services import audit
from conftest import DEV, HR, ORG_A, ORG_B, OWNER, headers, login


def senior(db):
    user = identifier()
    db.add(
        Membership(
            organization_id=ORG_A,
            user_id=user,
            email=user + "@example.org",
            role="senior_developer",
        )
    )
    db.commit()
    return user


def policy(client, count=2, members=False, version=1):
    login(OWNER)
    response = client.put(
        "/api/v1/devtrack/approval-policy",
        headers=headers(),
        json={
            "version": version,
            "required_senior_reviews": count,
            "reviewers_must_be_members": members,
        },
    )
    assert response.status_code == 201, response.text


def propose(client):
    login(DEV)
    response = client.post(
        "/api/v1/projects",
        headers=headers(),
        json={"name": "Proposal fixture", "description": "Synthetic proposal"},
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def test_distinct_active_reviews_are_required_and_policy_changes_do_not_rewrite_proposals(
    client, db
):
    policy(client, count=2)
    project = propose(client)
    policy(client, count=3, version=2)
    first, second, replacement = senior(db), senior(db), senior(db)
    decision = f"/api/v1/projects/{project}/decision"
    login(first)
    reviewed = client.post(decision, headers=headers(), json={"decision": "reviewed"})
    assert reviewed.status_code == 200 and reviewed.json()["status"] == "proposed"
    assert (
        client.post(decision, headers=headers(), json={"decision": "reviewed"}).status_code == 409
    )
    login(OWNER)
    assert (
        client.post(decision, headers=headers(), json={"decision": "approved"}).status_code == 409
    )
    login(second)
    response = client.post(
        f"/api/v1/projects/{project}/reviews",
        headers=headers(),
        json={"comment": "Independent review"},
    )
    assert response.json()["status"] == "reviewed"
    state = client.get(f"/api/v1/projects/{project}/reviews", headers=headers()).json()
    assert state["required_reviews"] == 2 and state["policy"]["version"] == 1
    db.get(Membership, (ORG_A, first)).active = False
    db.commit()
    login(OWNER)
    assert (
        client.post(decision, headers=headers(), json={"decision": "approved"}).status_code == 409
    )
    login(replacement)
    assert (
        client.post(decision, headers=headers(), json={"decision": "reviewed"}).status_code == 200
    )
    login(OWNER)
    assert (
        client.post(decision, headers=headers(), json={"decision": "approved"}).json()["status"]
        == "approved"
    )


def test_assigned_reviewer_policy_restricts_queue_and_review_access(client, db):
    policy(client, count=1, members=True)
    project = propose(client)
    reviewer = senior(db)
    login(reviewer)
    assert client.get("/api/v1/devtrack/review-queue", headers=headers()).json() == []
    assert (
        client.post(f"/api/v1/projects/{project}/reviews", headers=headers(), json={}).status_code
        == 403
    )
    assert client.get(f"/api/v1/projects/{project}/reviews", headers=headers()).status_code == 404
    login(OWNER)
    assert (
        client.post(
            f"/api/v1/projects/{project}/members",
            headers=headers(),
            json={"user_id": reviewer, "manager": False},
        ).status_code
        == 201
    )
    login(reviewer)
    assert client.get("/api/v1/devtrack/review-queue", headers=headers()).json()[0]["id"] == project
    assert (
        client.post(f"/api/v1/projects/{project}/reviews", headers=headers(), json={}).status_code
        == 200
    )


def test_project_activity_is_resource_scoped_without_exposing_hr_audit(client, db):
    project = propose(client)
    response = client.get(f"/api/v1/projects/{project}/activity", headers=headers())
    assert response.status_code == 200
    assert response.json()[0]["action"] == "project.created"
    assert (
        client.get(f"/api/v1/projects/{project}/activity", headers=headers(ORG_B)).status_code
        == 404
    )
    other = senior(db)
    login(other)
    assert client.get(f"/api/v1/projects/{project}/activity", headers=headers()).status_code == 404


def test_policy_configuration_is_owner_only_monotonic_and_tenant_scoped(client):
    policy(client, count=2)
    assert (
        client.get("/api/v1/devtrack/approval-policy", headers=headers(ORG_B)).json()["version"]
        == 0
    )
    assert (
        client.put(
            "/api/v1/devtrack/approval-policy", headers=headers(), json={"version": 1}
        ).status_code
        == 409
    )
    login(HR)
    assert (
        client.put(
            "/api/v1/devtrack/approval-policy", headers=headers(), json={"version": 2}
        ).status_code
        == 403
    )


def test_legacy_review_history_is_preserved_without_fabricated_review_records(client, db):
    reviewer = senior(db)
    record = Project(
        id=identifier(),
        organization_id=ORG_A,
        proposer_id=DEV,
        name="Legacy fixture",
        description="Historical proposal",
        status="reviewed",
    )
    db.add(record)
    db.flush()
    audit(db, Principal(reviewer, ORG_A, "senior_developer"), "project.reviewed", record.id)
    db.commit()
    login(OWNER)
    response = client.post(
        f"/api/v1/projects/{record.id}/decision", headers=headers(), json={"decision": "approved"}
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "approved"
