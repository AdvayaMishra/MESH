from app.models import Finding, Repository, identifier
from conftest import ANALYST, DEV, ORG_A, ORG_B, OWNER, headers, login


def test_analytics_counts_repeat_findings_without_leaking_other_repositories_or_tenants(client, db):
    repositories = []
    for org in [ORG_A, ORG_A, ORG_B]:
        repository = Repository(
            id=identifier(),
            organization_id=org,
            full_name="fixture/" + identifier(),
            installation_id=1,
        )
        db.add(repository)
        repositories.append(repository)
    db.flush()
    for index, repo in enumerate(repositories):
        for severity, status in [("high", "open"), ("high", "resolved"), ("info", "open")][
            : 3 - index
        ]:
            db.add(
                Finding(
                    organization_id=repo.organization_id,
                    repository_id=repo.id,
                    scanner="bandit",
                    rule_id="fixture",
                    severity=severity,
                    status=status,
                    file_path="fixture.py",
                    line=1,
                )
            )
    db.commit()
    login(ANALYST)
    endpoint = f"/api/v1/repositories/{repositories[0].id}/analytics"
    result = client.get(endpoint, headers=headers())
    assert result.status_code == 200
    assert result.json() == {
        "severity": {"high": 2, "info": 1},
        "status": {"open": 2, "resolved": 1},
    }
    assert client.get(endpoint, headers=headers(ORG_B)).status_code == 404
    login(DEV)
    assert client.get(endpoint, headers=headers()).status_code == 403
    login(OWNER)
    assert client.get(endpoint, headers=headers()).status_code == 403
