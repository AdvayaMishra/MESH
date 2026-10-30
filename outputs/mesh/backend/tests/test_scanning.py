import json

import httpx
import pytest
from app.models import Repository, identifier
from app.scanning import OSV, DockerSandbox, normalize
from conftest import ANALYST, ORG_A, ORG_B, headers, login


@pytest.mark.parametrize(
    "scanner,raw",
    [
        (
            "semgrep",
            {
                "results": [
                    {
                        "path": "/repo/a.py",
                        "start": {"line": 2},
                        "check_id": "dynamic-eval",
                        "extra": {"severity": "ERROR", "lines": "TOP_SECRET"},
                    }
                ]
            },
        ),
        (
            "bandit",
            {
                "results": [
                    {
                        "filename": "/repo/a.py",
                        "line_number": 2,
                        "test_id": "B307",
                        "issue_severity": "HIGH",
                        "code": "TOP_SECRET",
                    }
                ]
            },
        ),
        (
            "gitleaks",
            [
                {
                    "File": "a.py",
                    "StartLine": 2,
                    "RuleID": "key",
                    "Secret": "TOP_SECRET",
                    "Match": "TOP_SECRET",
                }
            ],
        ),
    ],
)
def test_scanner_adapters_strip_source_and_secrets(scanner, raw):
    results = normalize(scanner, raw)
    assert results[0]["file_path"] == "a.py"
    assert "TOP_SECRET" not in json.dumps(results)


def test_docker_containment_arguments():
    command = DockerSandbox().command("test", "mesh-01234567", "bandit")
    for control in (
        "--network=none",
        "--read-only",
        "--cap-drop=ALL",
        "--security-opt=no-new-privileges",
        "--pids-limit=128",
        "--memory=768m",
        "--memory-swap=768m",
        "--cpus=1",
    ):
        assert control in command
    assert all(
        name + "=" in command
        for name in (
            "HTTP_PROXY",
            "HTTPS_PROXY",
            "ALL_PROXY",
            "http_proxy",
            "https_proxy",
            "all_proxy",
        )
    )
    assert "readonly" in next(item for item in command if "dst=/repo" in item)
    assert not any("docker.sock" in item for item in command)
    with pytest.raises(ValueError):
        DockerSandbox().command("test", "../../host", "bandit")


def test_incomplete_analysis_never_becomes_clean_result():
    with pytest.raises(ValueError, match="incomplete"):
        normalize("bandit", {"results": [], "errors": [{"reason": "parse failure"}]})


def test_osv_only_sends_dependency_metadata():
    def handler(request):
        assert request.url == "https://api.osv.dev/v1/querybatch"
        assert json.loads(request.content) == {
            "queries": [{"package": {"name": "example", "ecosystem": "PyPI"}, "version": "1.0"}]
        }
        return httpx.Response(200, json={"results": [{"vulns": [{"id": "OSV-EXAMPLE"}]}]})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = OSV(client).check([{"name": "example", "ecosystem": "PyPI", "version": "1.0"}])
    assert result[0]["rule_id"] == "OSV-EXAMPLE"


@pytest.mark.parametrize(
    "result",
    [
        None,
        [1],
        [{"error": "unavailable"}],
        [{"vulns": [{"id": "bad\nvalue"}]}],
        [{"next_page_token": 7}],
    ],
)
def test_osv_invalid_partial_results_never_mean_clean(result):
    with httpx.Client(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json={"results": result}))
    ) as client:
        with pytest.raises(ValueError):
            OSV(client).check([{"name": "example", "ecosystem": "PyPI", "version": "1"}])


def test_osv_redirect_is_not_followed_even_with_injected_redirect_client():
    calls = []

    def handler(request):
        calls.append(str(request.url))
        return httpx.Response(307, headers={"location": "https://other.invalid/collect"})

    with httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True) as client:
        with pytest.raises(httpx.HTTPStatusError):
            OSV(client).check([{"name": "example", "ecosystem": "PyPI", "version": "1"}])
    assert calls == ["https://api.osv.dev/v1/querybatch"]


def test_scan_request_idempotency_and_cross_tenant(client, db):
    repository = Repository(
        id=identifier(),
        organization_id=ORG_A,
        full_name="org/repo",
        installation_id=1,
        enabled=True,
    )
    db.add(repository)
    db.commit()
    login(ANALYST)
    data = {"repository_id": repository.id, "commit_sha": "a" * 40, "request_key": "request-12345"}
    created = client.post("/api/v1/scans", headers=headers(), json=data)
    assert created.status_code == 202, created.text
    assert (
        client.post("/api/v1/scans", headers=headers(), json=data).json()["id"]
        == created.json()["id"]
    )
    assert (
        client.post(
            "/api/v1/scans", headers=headers(), json={**data, "commit_sha": "b" * 40}
        ).status_code
        == 409
    )
    assert (
        client.get("/api/v1/scans/" + created.json()["id"], headers=headers(ORG_B)).status_code
        == 404
    )
