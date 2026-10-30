from datetime import timedelta

from app.models import Finding, Repository, ScanJob, identifier, now
from conftest import ANALYST, DEV, ORG_A, ORG_B, OWNER, headers, login


def seed(db):
    repos = [
        Repository(organization_id=org, full_name="fixture/" + identifier(), installation_id=1)
        for org in (ORG_A, ORG_A, ORG_B)
    ]
    db.add_all(repos)
    db.flush()
    timestamp = now()
    for index, repo in enumerate(repos):
        for state in ("open", "open", "triaged", "resolved", "false_positive"):
            db.add(
                Finding(
                    organization_id=repo.organization_id,
                    repository_id=repo.id,
                    scanner="bandit",
                    rule_id="B602",
                    severity="high",
                    status=state,
                    file_path="fixture.py",
                    line=1,
                    created_at=timestamp - timedelta(days=index),
                )
            )
    db.add(
        Finding(
            organization_id=ORG_A,
            repository_id=repos[0].id,
            scanner="osv",
            rule_id="fixture",
            severity="critical",
            status="open",
            file_path="dependency-manifest",
            line=0,
            created_at=timestamp - timedelta(days=10),
        )
    )
    db.commit()
    login(ANALYST)
    return repos, timestamp


def test_remediation_group_counts_scope_and_pagination(client, db):
    repos, _ = seed(db)
    endpoint = f"/api/v1/repositories/{repos[0].id}/remediation"
    response = client.get(endpoint + "?limit=1", headers=headers())
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["total_groups"] == 2 and result["counting"] == "finding_observations"
    group = result["groups"][0]
    assert {
        key: group[key] for key in ("open", "triaged", "resolved", "false_positive", "total")
    } == {
        "open": 2,
        "triaged": 1,
        "resolved": 1,
        "false_positive": 1,
        "total": 5,
    }
    assert group["first_observed_at"] == group["last_observed_at"]
    second = client.get(endpoint + "?limit=1&offset=1", headers=headers()).json()
    assert second["groups"][0]["scanner"] == "osv" and second["total_groups"] == 2
    beyond = client.get(endpoint + "?offset=10", headers=headers()).json()
    assert beyond["groups"] == [] and beyond["total_groups"] == 2
    assert client.get(endpoint, headers=headers(ORG_B)).status_code == 404
    login(OWNER)
    assert client.get(endpoint, headers=headers()).status_code == 403
    login(DEV)
    assert client.get(endpoint, headers=headers()).status_code == 403


def test_remediation_filters_and_rejects_ambiguous_time(client, db):
    repos, timestamp = seed(db)
    endpoint = f"/api/v1/repositories/{repos[0].id}/remediation"
    response = client.get(
        endpoint,
        headers=headers(),
        params={
            "scanner": "bandit",
            "severity": "high",
            "observed_since": (timestamp - timedelta(days=1)).isoformat(),
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["total_groups"] == 1
    assert response.json()["groups"][0]["total"] == 5
    assert client.get(endpoint + "?scanner=gitleaks", headers=headers()).json()["groups"] == []
    for params in ({"observed_since": "2026-10-25T00:00:00"}, {"scanner": "other"}, {"limit": 0}):
        assert client.get(endpoint, params=params, headers=headers()).status_code == 422


def test_scan_history_filters_pagination_and_cross_repository_isolation(client, db):
    repos, _ = seed(db)
    for repo in repos:
        for state, actor, attempts in (
            ("failed", ANALYST, 2),
            ("completed", ANALYST, 1),
            ("failed", OWNER, 3),
        ):
            db.add(
                ScanJob(
                    organization_id=repo.organization_id,
                    repository_id=repo.id,
                    requested_by=actor,
                    request_key=identifier(),
                    commit_sha="a" * 40,
                    status=state,
                    attempts=attempts,
                )
            )
    db.commit()
    endpoint = f"/api/v1/repositories/{repos[0].id}/scans"
    response = client.get(
        endpoint,
        headers=headers(),
        params={
            "status": "failed",
            "requested_by": ANALYST,
            "sort_by": "attempts",
            "direction": "desc",
        },
    )
    assert response.status_code == 200, response.text
    assert len(response.json()) == 1 and response.json()[0]["attempts"] == 2
    response = client.get(
        endpoint + "?sort_by=attempts&direction=desc&limit=1&offset=1", headers=headers()
    )
    assert response.json()[0]["attempts"] == 2
    assert client.get(endpoint, headers=headers(ORG_B)).status_code == 404
    for params in ({"status": "invalid"}, {"sort_by": "report"}, {"direction": "sideways"}):
        assert client.get(endpoint, params=params, headers=headers()).status_code == 422
