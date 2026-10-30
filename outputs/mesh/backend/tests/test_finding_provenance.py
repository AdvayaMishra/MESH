import json

import httpx
import pytest
from app.models import Finding, Repository, ScanJob, identifier
from app.scanning import OSV, normalize
from conftest import ANALYST, ORG_A, ORG_B, headers, login
from sqlalchemy.exc import IntegrityError


def test_osv_pagination_retains_the_correct_package_and_deduplicates_only_exact_matches():
    calls = []

    def handler(request):
        queries = json.loads(request.content)["queries"]
        calls.append(queries)
        assert "PRIVATE_SOURCE" not in request.content.decode()
        if len(calls) == 1:
            return httpx.Response(
                200,
                json={
                    "results": [
                        {"vulns": [{"id": "OSV-SHARED"}], "next_page_token": "next-a"},
                        {"vulns": [{"id": "OSV-SHARED"}]},
                    ]
                },
            )
        assert queries == [
            {
                "package": {"name": "package-a", "ecosystem": "PyPI"},
                "version": "1.0",
                "page_token": "next-a",
            }
        ]
        return httpx.Response(
            200, json={"results": [{"vulns": [{"id": "OSV-SHARED"}, {"id": "OSV-SECOND"}]}]}
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        rows = OSV(client).check(
            [
                {
                    "name": "package-a",
                    "ecosystem": "PyPI",
                    "version": "1.0",
                    "private": "PRIVATE_SOURCE",
                },
                {"name": "package-b", "ecosystem": "npm", "version": "2.0"},
            ]
        )
    assert len(rows) == 3
    assert [
        (row["dependency"]["name"], row["dependency"]["version"], row["rule_id"]) for row in rows
    ] == [
        ("package-a", "1.0", "OSV-SHARED"),
        ("package-b", "2.0", "OSV-SHARED"),
        ("package-a", "1.0", "OSV-SECOND"),
    ]
    assert all(set(row["dependency"]) == {"name", "ecosystem", "version"} for row in rows)


def test_osv_never_merges_the_same_advisory_across_different_package_versions():
    with httpx.Client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                json={
                    "results": [
                        {"vulns": [{"id": "OSV-SHARED"}]},
                        {"vulns": [{"id": "OSV-SHARED"}]},
                    ]
                },
            )
        )
    ) as client:
        rows = OSV(client).check(
            [
                {"name": "package-a", "ecosystem": "PyPI", "version": version}
                for version in ("1.0", "2.0")
            ]
        )
    assert [row["dependency"]["version"] for row in rows] == ["1.0", "2.0"]


@pytest.mark.parametrize(
    "scanner,report,column",
    [
        (
            "semgrep",
            {
                "results": [
                    {
                        "path": "a.py",
                        "start": {"line": 2, "col": 4},
                        "check_id": "rule",
                        "extra": {"severity": "WARNING"},
                    }
                ]
            },
            4,
        ),
        (
            "bandit",
            {
                "results": [
                    {
                        "filename": "a.py",
                        "line_number": 2,
                        "col_offset": 0,
                        "test_id": "B307",
                        "issue_severity": "HIGH",
                    }
                ]
            },
            1,
        ),
        (
            "gitleaks",
            [
                {
                    "File": "a.py",
                    "StartLine": 2,
                    "StartColumn": 8,
                    "RuleID": "rule",
                    "Secret": "PRIVATE_SECRET",
                }
            ],
            8,
        ),
    ],
)
def test_column_positions_are_retained_without_secret_evidence(scanner, report, column):
    row = normalize(scanner, report)[0]
    assert row["column"] == column and "PRIVATE_SECRET" not in json.dumps(row)


def records(db):
    repositories = [
        Repository(
            id=identifier(),
            organization_id=org,
            full_name=f"fixture/repo-{i}",
            installation_id=1,
            enabled=True,
        )
        for i, org in enumerate((ORG_A, ORG_A, ORG_B))
    ]
    db.add_all(repositories)
    db.flush()
    jobs = [
        ScanJob(
            id=identifier(),
            organization_id=repo.organization_id,
            repository_id=repo.id,
            requested_by=ANALYST,
            request_key=identifier(),
            commit_sha=letter * 40,
        )
        for repo, letter in zip(repositories, "abc", strict=True)
    ]
    db.add_all(jobs)
    db.commit()
    return repositories, jobs


def finding(repo, job=None, **values):
    return Finding(
        organization_id=repo.organization_id,
        repository_id=repo.id,
        scanner="osv",
        rule_id="OSV-SHARED",
        severity="info",
        file_path="dependency-manifest",
        line=1,
        scan_job_id=job.id if job else None,
        commit_sha=job.commit_sha if job else None,
        **values,
    )


def test_finding_filters_preserve_exact_provenance_and_legacy_unknowns(client, db):
    repos, jobs = records(db)
    linked = finding(
        repos[0], jobs[0], dependency={"name": "package-a", "ecosystem": "PyPI", "version": "1.0"}
    )
    legacy = finding(repos[0])
    db.add_all(
        [
            linked,
            legacy,
            finding(
                repos[2],
                jobs[2],
                dependency={"name": "private-b", "ecosystem": "npm", "version": "2"},
            ),
        ]
    )
    db.commit()
    login(ANALYST)
    base = f"/api/v1/repositories/{repos[0].id}/findings"
    rows = client.get(base, headers=headers()).json()
    assert len(rows) == 2
    assert next(row for row in rows if row["id"] == legacy.id)["scan_job_id"] is None
    filtered = client.get(
        base,
        headers=headers(),
        params={"scan_job_id": jobs[0].id, "commit_sha": "a" * 40, "dependency_name": "package-a"},
    ).json()
    assert len(filtered) == 1 and filtered[0]["id"] == linked.id
    assert filtered[0]["dependency"]["version"] == "1.0"
    assert client.get(base, headers=headers(), params={"scan_job_id": jobs[2].id}).json() == []
    assert client.get(base, headers=headers(ORG_B)).status_code == 404
    assert client.get(base, headers=headers(), params={"commit_sha": "main"}).status_code == 422
    assert (
        client.patch(
            f"/api/v1/findings/{linked.id}",
            headers=headers(),
            json={"status": "resolved", "commit_sha": "b" * 40},
        ).status_code
        == 422
    )


@pytest.mark.parametrize(
    "mismatch", ["repository", "tenant", "commit", "half_provenance", "column"]
)
def test_database_rejects_cross_scope_or_incomplete_finding_provenance(db, mismatch):
    repos, jobs = records(db)
    row = finding(repos[0], jobs[0])
    if mismatch == "repository":
        row.scan_job_id, row.commit_sha = jobs[1].id, jobs[1].commit_sha
    elif mismatch == "tenant":
        row.scan_job_id, row.commit_sha = jobs[2].id, jobs[2].commit_sha
    elif mismatch == "commit":
        row.commit_sha = "f" * 40
    elif mismatch == "half_provenance":
        row.commit_sha = None
    else:
        row.column = 0
    with pytest.raises(IntegrityError), db.begin_nested():
        db.add(row)
        db.flush()
