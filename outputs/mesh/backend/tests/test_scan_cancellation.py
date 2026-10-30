from datetime import timedelta

import pytest
from app.models import AuditLog, Finding, Membership, ScanJob, now
from app.scan_worker import run_once
from conftest import ANALYST, DEV, ORG_A, ORG_B, OWNER, headers, login
from sqlalchemy import select
from test_scan_progress import prepare


@pytest.mark.parametrize("state", ["queued", "running"])
def test_cancel_is_idempotent_clears_lease_and_audits_once(client, db, monkeypatch, state):
    job, _ = prepare(db, monkeypatch)
    job.status = state
    job.lease_until = now() + timedelta(minutes=30)
    job.report = {"stage": "bandit", "progress": 40, "completed_steps": ["checkout", "semgrep"]}
    db.commit()
    login(ANALYST)
    endpoint = f"/api/v1/scans/{job.id}/cancel"
    for _ in range(2):
        response = client.post(endpoint, headers=headers())
        assert response.status_code == 200, response.text
        assert response.json()["status"] == "cancelled"
        assert response.json()["report"]["progress"] == 40
    assert db.get(ScanJob, job.id).lease_until is None
    audits = db.scalars(
        select(AuditLog).where(AuditLog.action == "repository.scan.cancelled")
    ).all()
    assert len(audits) == 1
    assert run_once(ORG_A) is False


@pytest.mark.parametrize("state", ["completed", "dead_letter"])
def test_cancel_preserves_terminal_history(client, db, monkeypatch, state):
    job, _ = prepare(db, monkeypatch)
    job.status = state
    db.commit()
    login(ANALYST)
    assert client.post(f"/api/v1/scans/{job.id}/cancel", headers=headers()).status_code == 409
    assert db.get(ScanJob, job.id).status == state


def test_cancellation_enforces_tenant_role_and_repository_assignment(client, db, monkeypatch):
    job, _ = prepare(db, monkeypatch)
    endpoint = f"/api/v1/scans/{job.id}/cancel"
    login(ANALYST)
    assert client.post(endpoint, headers=headers(ORG_B)).status_code == 404
    login(OWNER)
    assert client.post(endpoint, headers=headers()).status_code == 403
    member = db.get(Membership, (ORG_A, DEV))
    member.role = "senior_developer"
    db.commit()
    login(DEV)
    assert client.post(endpoint, headers=headers()).status_code == 404
    assert db.get(ScanJob, job.id).status == "queued"


def test_running_worker_cannot_commit_findings_after_authorized_cancellation(
    client, db, monkeypatch
):
    job, _ = prepare(db, monkeypatch)
    login(ANALYST)

    def runner(repository, commit, token):
        response = client.post(f"/api/v1/scans/{job.id}/cancel", headers=headers())
        assert response.status_code == 200, response.text
        return {
            "completed": ["semgrep", "bandit", "gitleaks", "osv"],
            "findings": [
                {
                    "scanner": "bandit",
                    "rule_id": "fixture",
                    "severity": "high",
                    "file_path": "fixture.py",
                    "line": 1,
                }
            ],
        }

    assert run_once(ORG_A, runner=runner)
    db.expire_all()
    assert db.get(ScanJob, job.id).status == "cancelled"
    assert not db.scalars(select(Finding)).all()
