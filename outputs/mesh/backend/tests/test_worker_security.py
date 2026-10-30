import io
import json
import subprocess
import sys

import pytest
from app.models import Finding, Membership, Repository, ScanJob, identifier
from app.scan_worker import run_once
from app.scanning import DockerSandbox, normalize
from conftest import ANALYST, ORG_A
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker


def test_real_bandit_fixture_without_executing_code(tmp_path):
    fixture = tmp_path / "fixture.py"
    fixture.write_text("eval('input()')\n", encoding="utf-8")
    result = subprocess.run(
        [sys.executable, "-m", "bandit", "-r", str(tmp_path), "-f", "json"],
        capture_output=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 1
    report = json.loads(result.stdout)
    # Normalize a path relative to the scanner's container root, never expose the host fixture path.
    for item in report["results"]:
        item["filename"] = "fixture.py"
    assert any(item["rule_id"] == "B307" for item in normalize("bandit", report))


def test_scanner_output_bound_and_cleanup(monkeypatch):
    monkeypatch.setattr(DockerSandbox, "verify_host", lambda self: None)
    calls = []

    class Process:
        stdout = io.BytesIO(b"x" * 100)

        def poll(self):
            return 0

        def wait(self, timeout):
            return 0

    monkeypatch.setattr("app.scanning.subprocess.Popen", lambda *a, **k: Process())
    monkeypatch.setattr("app.scanning.subprocess.run", lambda command, **k: calls.append(command))
    with pytest.raises(RuntimeError, match="output exceeded"):
        DockerSandbox(max_output=50).execute("mesh-12345", "bandit")
    assert calls and calls[-1][1:3] == ["rm", "-f"]


@pytest.mark.parametrize("revoke_during_scan", [False, True])
def test_scan_worker_rechecks_authorization_and_is_idempotent(db, monkeypatch, revoke_during_scan):
    repository = Repository(
        id=identifier(),
        organization_id=ORG_A,
        full_name="org/repo",
        installation_id=1,
        enabled=True,
    )
    db.add(repository)
    db.flush()
    job = ScanJob(
        id=identifier(),
        organization_id=ORG_A,
        repository_id=repository.id,
        requested_by=ANALYST,
        request_key="test-worker-key",
        commit_sha="a" * 40,
    )
    db.add(job)
    db.commit()
    factory = sessionmaker(db.get_bind(), expire_on_commit=False)
    monkeypatch.setattr("app.scan_worker.SessionFactory", factory)
    monkeypatch.setattr("app.scan_worker.GitHubApp.token", lambda *a: "ephemeral-test-token")

    def runner(repo, commit, token):
        assert commit == "a" * 40 and token == "ephemeral-test-token"
        if revoke_during_scan:
            with factory.begin() as session:
                session.get(Membership, (ORG_A, ANALYST)).active = False
        return {
            "completed": ["bandit"],
            "findings": [
                {
                    "scanner": "bandit",
                    "rule_id": "B307",
                    "severity": "high",
                    "file_path": "a.py",
                    "line": 1,
                }
            ],
        }

    assert run_once(ORG_A, runner)
    db.expire_all()
    assert db.get(ScanJob, job.id).status == ("cancelled" if revoke_during_scan else "completed")
    assert len(db.scalars(select(Finding)).all()) == (0 if revoke_during_scan else 1)
    if not revoke_during_scan:
        result = db.scalars(select(Finding)).one()
        assert result.scan_job_id == job.id and result.commit_sha == "a" * 40
    assert not run_once(ORG_A, runner)
