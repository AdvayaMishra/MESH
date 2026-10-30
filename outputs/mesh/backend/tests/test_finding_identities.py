from datetime import timedelta

import pytest
from app.auth import Principal
from app.finding_identity import index_observations, link_observations
from app.models import Finding, FindingIdentity, Membership, Repository, ScanJob, identifier, now
from app.scan_worker import run_once
from conftest import ANALYST, HR, ORG_A, ORG_B, OWNER, headers, login
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker


@pytest.fixture
def repository(db):
    repo = Repository(
        id=identifier(),
        organization_id=ORG_A,
        full_name="fixture/identities",
        installation_id=1,
        enabled=True,
    )
    db.add(repo)
    db.commit()
    login(ANALYST)
    return repo


def observation(repo, **values):
    return Finding(
        organization_id=repo.organization_id,
        repository_id=repo.id,
        scanner="bandit",
        rule_id="B307",
        file_path="a.py",
        line=10,
        severity="high",
        **values,
    )


def test_bounded_indexing_retains_legacy_provenance_and_historical_dispositions(
    client, db, repository
):
    start = now() - timedelta(days=1)
    first = observation(repository, created_at=start, status="open")
    second = observation(repository, created_at=start + timedelta(hours=1), status="resolved")
    third = observation(repository, created_at=start + timedelta(hours=2), column=2)
    db.add_all([first, second, third])
    db.commit()
    base = f"/api/v1/repositories/{repository.id}/finding-identities"
    assert client.get(base, headers=headers()).json()["unindexed_observations"] == 3
    partial = client.post(base + "/index", headers=headers(), json={"limit": 1})
    assert partial.status_code == 200 and partial.json()["linked_observations"] == 1
    assert partial.json()["remaining_unindexed"] == 2
    assert (
        client.post(base + "/index", headers=headers(), json={"limit": 500}).json()[
            "linked_observations"
        ]
        == 2
    )
    assert (
        client.post(base + "/index", headers=headers(), json={"limit": 500}).json()[
            "linked_observations"
        ]
        == 0
    )
    assert db.query(FindingIdentity).count() == 2
    assert first.scan_job_id is None and second.commit_sha is None
    result = client.get(base, headers=headers()).json()
    assert result["total_groups"] == 2 and result["unindexed_observations"] == 0
    shared = next(group for group in result["groups"] if group["match"]["column"] is None)
    assert shared["observations"] == 2 and shared["distinct_scans"] == 0
    assert shared["observations_without_scan_provenance"] == 2
    assert (
        shared["latest_status"] == "resolved"
        and shared["statuses"]["open"] == 1
        and shared["statuses"]["resolved"] == 1
    )
    history = client.get(
        f"/api/v1/finding-identities/{shared['id']}/observations", headers=headers()
    ).json()
    assert history["total_observations"] == 2
    assert [row["id"] for row in history["observations"]] == [first.id, second.id]
    assert all(row["scan_job_id"] is None for row in history["observations"])
    filtered = client.get(base, headers=headers(), params={"status": "resolved"}).json()
    assert filtered["total_groups"] == 1 and filtered["groups"][0]["id"] == shared["id"]
    assert client.get(base, headers=headers(), params={"offset": 100}).json()["total_groups"] == 2
    assert client.get(base, headers=headers(), params={"offset": 100}).json()["groups"] == []


def test_new_scans_share_identity_but_never_inherit_resolved_disposition(
    client, db, repository, monkeypatch
):
    factory = sessionmaker(db.get_bind(), expire_on_commit=False)
    monkeypatch.setattr("app.scan_worker.SessionFactory", factory)
    monkeypatch.setattr(
        "app.scan_worker.GitHubApp.token", lambda *args: "synthetic-read-only-token"
    )
    first = ScanJob(
        organization_id=ORG_A,
        repository_id=repository.id,
        requested_by=ANALYST,
        request_key=identifier(),
        commit_sha="a" * 40,
        created_at=now() - timedelta(minutes=2),
    )
    second = ScanJob(
        organization_id=ORG_A,
        repository_id=repository.id,
        requested_by=ANALYST,
        request_key=identifier(),
        commit_sha="b" * 40,
        created_at=now() - timedelta(minutes=1),
    )
    db.add_all([first, second])
    db.commit()

    def runner(*args):
        return {
            "completed": ["bandit"],
            "findings": [
                {
                    "scanner": "bandit",
                    "rule_id": "B307",
                    "file_path": "a.py",
                    "line": 10,
                    "column": 2,
                    "severity": "high",
                }
            ],
        }

    assert run_once(ORG_A, runner)
    db.expire_all()
    original = db.scalar(select(Finding))
    assert (
        client.patch(
            f"/api/v1/findings/{original.id}", headers=headers(), json={"status": "resolved"}
        ).status_code
        == 200
    )
    assert run_once(ORG_A, runner)
    db.expire_all()
    rows = db.scalars(select(Finding)).all()
    assert len(rows) == 2 and len({row.identity_id for row in rows}) == 1
    assert {row.status for row in rows} == {"open", "resolved"}
    groups = client.get(
        f"/api/v1/repositories/{repository.id}/finding-identities", headers=headers()
    ).json()
    assert groups["groups"][0]["distinct_scans"] == 2
    assert (
        groups["groups"][0]["latest_status"] == "open"
        and groups["groups"][0]["latest_commit_sha"] == "b" * 40
    )


def test_package_and_version_are_part_of_identity_but_severity_is_not(db, repository):
    rows = [
        Finding(
            organization_id=ORG_A,
            repository_id=repository.id,
            scanner="osv",
            rule_id="OSV-SHARED",
            file_path="dependency-manifest",
            line=1,
            severity=severity,
            dependency={"name": name, "ecosystem": "PyPI", "version": version},
        )
        for name, version, severity in (
            ("a", "1", "info"),
            ("b", "1", "info"),
            ("a", "2", "info"),
            ("a", "1", "high"),
        )
    ]
    link_observations(db, ORG_A, repository.id, rows)
    db.add_all(rows)
    db.commit()
    assert len({row.identity_id for row in rows}) == 3
    assert rows[0].identity_id == rows[3].identity_id


@pytest.mark.parametrize("role", [HR, OWNER])
def test_identity_index_and_history_obey_tenant_and_role_permissions(client, db, repository, role):
    row = observation(repository)
    db.add(row)
    db.commit()
    base = f"/api/v1/repositories/{repository.id}/finding-identities"
    assert client.post(base + "/index", headers=headers(), json={"limit": 5}).status_code == 200
    identity = row.identity_id
    assert client.get(base, headers=headers(ORG_B)).status_code == 404
    assert (
        client.get(
            f"/api/v1/finding-identities/{identity}/observations", headers=headers(ORG_B)
        ).status_code
        == 404
    )
    login(role)
    assert client.get(base, headers=headers()).status_code == 403
    assert client.post(base + "/index", headers=headers(), json={"limit": 1}).status_code == 403


def test_identity_index_rechecks_stale_authority_and_bounded_input(client, db, repository):
    db.add(observation(repository))
    db.commit()
    base = f"/api/v1/repositories/{repository.id}/finding-identities/index"
    for body in ({"limit": 0}, {"limit": 501}, {"limit": 5, "organization_id": ORG_B}):
        assert client.post(base, headers=headers(), json=body).status_code == 422
    stale = Principal(ANALYST, ORG_A, "security_analyst")
    db.get(Membership, (ORG_A, ANALYST)).role = "junior_developer"
    db.commit()
    with pytest.raises(HTTPException) as error:
        index_observations(db, stale, repository.id, 5)
    assert error.value.status_code == 403 and db.query(FindingIdentity).count() == 0


def test_identity_cannot_be_attached_to_another_repository(db, repository):
    row = observation(repository)
    link_observations(db, ORG_A, repository.id, [row])
    other = Repository(
        organization_id=ORG_A, full_name="fixture/other-identities", installation_id=1
    )
    db.add(other)
    db.flush()
    with pytest.raises(IntegrityError), db.begin_nested():
        db.add(observation(other, identity_id=row.identity_id))
        db.flush()
