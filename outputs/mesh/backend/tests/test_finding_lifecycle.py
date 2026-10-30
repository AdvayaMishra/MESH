from datetime import timedelta

import pytest
from app.finding_states import FINDING_STATES
from app.models import AuditLog, Finding, Repository, identifier, now
from app.risk_engine import collect
from conftest import ANALYST, DEV, ORG_A, ORG_B, OWNER, headers, login
from sqlalchemy import func, select


def fixture(db):
    repo = Repository(
        id=identifier(), organization_id=ORG_A, full_name="fixture/lifecycle", installation_id=1
    )
    db.add(repo)
    db.flush()
    record = Finding(
        id=identifier(),
        organization_id=ORG_A,
        repository_id=repo.id,
        scanner="bandit",
        rule_id="fixture",
        severity="high",
        file_path="fixture.py",
        line=1,
    )
    db.add(record)
    db.commit()
    login(ANALYST)
    return repo, record


def test_all_states_record_explicit_actor_before_after_and_same_state_is_noop(client, db):
    repo, record = fixture(db)
    endpoint = f"/api/v1/findings/{record.id}"
    previous = "open"
    for state in FINDING_STATES[1:]:
        response = client.patch(endpoint, headers=headers(), json={"status": state})
        assert response.status_code == 200, response.text
        history = client.get(endpoint + "/history", headers=headers()).json()
        change = history["changes"][-1]
        assert (change["from_status"], change["to_status"], change["actor_id"]) == (
            previous,
            state,
            ANALYST,
        )
        previous = state
    assert len(history["changes"]) == 6
    assert client.patch(endpoint, headers=headers(), json={"status": previous}).status_code == 200
    assert len(client.get(endpoint + "/history", headers=headers()).json()["changes"]) == 6
    assert (
        len(client.get(endpoint + "/history?limit=2&offset=2", headers=headers()).json()["changes"])
        == 2
    )
    rows = client.get(
        f"/api/v1/repositories/{repo.id}/findings?status=accepted_risk", headers=headers()
    ).json()
    assert len(rows) == 1 and rows[0]["status"] == "accepted_risk"
    assert "not independently verified" in history["resolution"]


@pytest.mark.parametrize(
    "actor,org,status", [(OWNER, ORG_A, 403), (DEV, ORG_A, 403), (ANALYST, ORG_B, 404)]
)
def test_lifecycle_and_history_do_not_cross_authorization_boundaries(
    client, db, actor, org, status
):
    _, record = fixture(db)
    login(actor)
    endpoint = f"/api/v1/findings/{record.id}"
    assert client.get(endpoint + "/history", headers=headers(org)).status_code == status
    assert (
        client.patch(endpoint, headers=headers(org), json={"status": "accepted_risk"}).status_code
        == status
    )
    assert (
        db.scalar(
            select(func.count())
            .select_from(AuditLog)
            .where(AuditLog.action.like("finding.transition.%"))
        )
        == 0
    )


def test_remediation_counts_new_states_without_claiming_verified_fixes(client, db):
    repo, record = fixture(db)
    for state in ("investigating", "confirmed", "accepted_risk"):
        db.add(
            Finding(
                organization_id=ORG_A,
                repository_id=repo.id,
                scanner="bandit",
                rule_id="fixture",
                severity="high",
                file_path="fixture.py",
                line=2,
                status=state,
            )
        )
    db.commit()
    response = client.get(f"/api/v1/repositories/{repo.id}/remediation", headers=headers())
    assert response.status_code == 200, response.text
    group = response.json()["groups"][0]
    assert group["total"] == 4 and group["resolved"] == 0
    assert all(
        group[state] == 1 for state in ("open", "investigating", "confirmed", "accepted_risk")
    )
    assert response.json()["counting"] == "finding_observations"


@pytest.mark.parametrize("state", FINDING_STATES)
def test_accepted_risk_and_investigation_remain_code_exposure(db, state):
    _, record = fixture(db)
    record.status = state
    db.commit()
    result = collect(db, ORG_A, now() - timedelta(hours=24), now(), False)
    component = result["code_security"]
    assert component["score"] == (None if state in {"resolved", "false_positive"} else 75)
