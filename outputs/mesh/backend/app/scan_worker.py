"""Dedicated trusted host launcher. Do not mount the Docker socket in the web/API container."""

import argparse
import subprocess  # nosec B404 # dedicated trusted Docker launcher, not an API host executor
from collections.abc import Callable
from datetime import datetime, timedelta
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import or_, select

from app.auth import Principal
from app.core.config import settings
from app.core.db import SessionFactory, assert_runtime_role, tenant_context
from app.core.time import as_utc
from app.devtrack import repository_access
from app.finding_identity import MAX_FINDINGS, NormalizedFinding, link_observations
from app.github import GitHubApp
from app.models import Finding, Membership, Organization, Repository, ScanJob, now
from app.scanning import OSV, DockerSandbox, normalize, resource_labels
from app.services import emit


def control(arguments: list[str]) -> None:
    subprocess.run(  # nosec B603 # callers supply only fixed Docker operations and generated resource names
        [settings().docker_executable, *arguments],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=240,
        check=True,
    )


SCAN_STEPS = ("checkout", "semgrep", "bandit", "gitleaks", "osv")


def verify_source_mount(name: str) -> None:
    result = subprocess.run(  # nosec B603 # generated owned keeper name, fixed inspect template
        [settings().docker_executable, "inspect", "--format", "{{.State.Running}}", name],
        capture_output=True,
        timeout=15,
        check=True,
    )
    if result.stdout.strip() != b"true":
        raise RuntimeError("Source volume keeper stopped")


def publish_progress(
    organization_id: str, job_id: str, lease: datetime, stage: str, finished: list[str]
) -> None:
    if finished != list(SCAN_STEPS[: len(finished)]) or len(finished) > len(SCAN_STEPS):
        raise ValueError("Invalid scan progress sequence")
    expected = SCAN_STEPS[len(finished)] if len(finished) < len(SCAN_STEPS) else "finalizing"
    if stage != expected:
        raise ValueError("Invalid scan progress stage")
    with SessionFactory.begin() as db:
        assert_runtime_role(db)
        tenant_context(db, organization_id, "scanner-worker")
        org = db.scalar(
            select(Organization)
            .where(Organization.id == organization_id)
            .with_for_update(key_share=True)
        )
        current = db.scalar(
            select(ScanJob)
            .where(ScanJob.organization_id == organization_id, ScanJob.id == job_id)
            .with_for_update()
        )
        if (
            current is None
            or current.status != "running"
            or current.lease_until is None
            or as_utc(current.lease_until) != as_utc(lease)
        ):
            raise PermissionError("Scan lease no longer belongs to this worker")
        member = db.get(Membership, (organization_id, current.requested_by))
        if org is None or org.status != "active" or member is None or not member.active:
            raise PermissionError("Scan access revoked")
        actor = Principal(member.user_id, organization_id, member.role)
        actor.require("repository.scan")
        if not repository_access(db, actor, current.repository_id, manage=True).enabled:
            raise PermissionError("Repository access revoked")
        current.report = {
            "stage": stage,
            "progress": min(95, 20 * len(finished)),
            "completed_steps": list(finished),
            "updated_at": now().isoformat(),
        }


def scan_repository(
    repository: Repository,
    commit: str,
    token: str,
    progress: Callable[[str, list[str]], None] | None = None,
) -> dict:
    sandbox = DockerSandbox(settings().scanner_image)
    sandbox.verify_host()  # Refuse checkout/token delivery on an unsupported host.
    if progress is not None:
        progress("checkout", [])
    volume = "mesh-" + str(uuid4())
    fetch_name = "mesh-fetch-" + uuid4().hex
    keeper_name = "mesh-keeper-" + uuid4().hex
    control(
        [
            "volume",
            "create",
            *resource_labels("source"),
            "--opt",
            "type=tmpfs",
            "--opt",
            "device=tmpfs",
            "--opt",
            "o=size=384m,uid=10001,gid=10001,mode=0700,noexec,nosuid,nodev",
            volume,
        ]
    )
    try:
        # A local tmpfs volume loses its contents when its last mount closes.
        # Keep one read-only mount alive across checkout and every scanner.
        keeper = sandbox.command(keeper_name, volume, "bandit")
        control(
            keeper[1:2]
            + ["--detach"]
            + keeper[2:-2]
            + [
                "--entrypoint=python",
                settings().scanner_image,
                "-c",
                "import time; time.sleep(1800)",
            ]
        )
        subprocess.run(  # nosec B603 # repository and commit are validated, no shell or user commands
            [
                settings().docker_executable,
                "run",
                "-i",
                "--name",
                fetch_name,
                *resource_labels("fetch"),
                "--rm",
                "--pull=never",
                "--read-only",
                "--user=10001:10001",
                "--cap-drop=ALL",
                "--security-opt=no-new-privileges",
                "--pids-limit=64",
                "--memory=512m",
                "--memory-swap=512m",
                "--cpus=1",
                "--tmpfs=/tmp:rw,noexec,nosuid,size=64m",
                "--mount",
                f"type=volume,src={volume},dst=/repo",
                "mesh-fetch:local",
                repository.full_name,
                commit,
            ],
            input=token.encode(),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=240,
            check=True,
        )
        findings = []
        completed: list[str] = []
        for scanner in ("semgrep", "bandit", "gitleaks"):
            verify_source_mount(keeper_name)
            if progress is not None:
                progress(scanner, ["checkout", *completed])
            findings.extend(normalize(scanner, sandbox.execute(volume, scanner)))
            completed.append(scanner)
        if progress is not None:
            progress("osv", ["checkout", *completed])
        findings.extend(OSV().check(sandbox.execute(volume, "dependencies")))
        verify_source_mount(keeper_name)
        if len(findings) > 20000:
            raise RuntimeError("Total finding count exceeded limit")
        completed.append("osv")
        if progress is not None:
            progress("finalizing", ["checkout", *completed])
        return {"findings": findings, "completed": completed}
    finally:
        subprocess.run(  # nosec B603 # generated keeper identifier only
            [settings().docker_executable, "rm", "-f", keeper_name],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=15,
            check=False,
        )
        subprocess.run(  # nosec B603 # generated container identifier only
            [settings().docker_executable, "rm", "-f", fetch_name],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=15,
            check=False,
        )
        subprocess.run(  # nosec B603 # owned generated tmpfs volume only
            [settings().docker_executable, "volume", "rm", "-f", volume],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=15,
            check=False,
        )


def run_once(organization_id: str, runner=None) -> bool:
    with SessionFactory.begin() as db:
        assert_runtime_role(db)
        tenant_context(db, organization_id, "scanner-worker")
        # Tenant lock serializes claims and completion against membership revocation.
        org = db.scalar(
            select(Organization)
            .where(Organization.id == organization_id)
            .with_for_update(key_share=True)
        )
        if org is None or org.status != "active":
            return False
        job = db.scalar(
            select(ScanJob)
            .where(
                ScanJob.organization_id == organization_id,
                or_(
                    (ScanJob.status == "queued")
                    & (ScanJob.lease_until.is_(None) | (ScanJob.lease_until <= now())),
                    (ScanJob.status == "running") & (ScanJob.lease_until < now()),
                ),
            )
            .order_by(ScanJob.created_at)
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        if job is None:
            return False
        member = db.get(Membership, (organization_id, job.requested_by))
        if member is None or not member.active:
            job.status = "cancelled"
            job.report = {"stage": "cancelled", "progress": 0}
            return True
        p = Principal(member.user_id, organization_id, member.role)
        try:
            p.require("repository.scan")
            repository = repository_access(db, p, job.repository_id, manage=True)
        except HTTPException:
            job.status = "cancelled"
            job.report = {"stage": "cancelled", "progress": 0}
            return True
        if not repository.enabled:
            job.status = "cancelled"
            job.report = {"stage": "cancelled", "progress": 0}
            return True
        if job.attempts >= 3:
            job.status, job.lease_until = "dead_letter", None
            job.report = {"error": "Scan lease recovery exhausted the attempt limit"}
            return True
        job.status, job.lease_until = "running", now() + timedelta(minutes=30)
        job.report = {"stage": "starting", "progress": 0, "completed_steps": []}
        job.attempts += 1
        job_id, lease, commit = job.id, job.lease_until, job.commit_sha
        # Detached snapshot; no secrets stored on ORM entity/database.
    try:
        token = GitHubApp().token(repository.installation_id, organization_id)
        if runner is None:
            report = scan_repository(
                repository,
                commit,
                token,
                progress=lambda stage, finished: publish_progress(
                    organization_id, job_id, lease, stage, finished
                ),
            )
        else:
            report = runner(repository, commit, token)
        if not isinstance(report.get("findings"), list) or len(report["findings"]) > MAX_FINDINGS:
            raise ValueError("Invalid or excessive scan observation inventory")
        report["findings"] = [
            NormalizedFinding.model_validate(row).model_dump(mode="json", exclude_none=True)
            for row in report["findings"]
        ]
        status = "completed"
    except Exception:
        report = {
            "error": "Scan failed; integration, timeout or scanner configuration requires review"
        }
        status = "dead_letter" if job.attempts >= 3 else "queued"
    with SessionFactory.begin() as db:
        tenant_context(db, organization_id, "scanner-worker")
        db.scalar(
            select(Organization)
            .where(Organization.id == organization_id)
            .with_for_update(key_share=True)
        )
        current = db.scalar(
            select(ScanJob)
            .where(ScanJob.organization_id == organization_id, ScanJob.id == job_id)
            .with_for_update()
        )
        if (
            current is None
            or current.repository_id != repository.id
            or current.commit_sha != commit
            or current.status != "running"
            or current.lease_until is None
            or as_utc(current.lease_until) != as_utc(lease)
        ):
            return True  # Lease fencing: a stale worker never commits another worker's result.
        active = db.get(Membership, (organization_id, current.requested_by))
        active_org = db.get(Organization, organization_id)
        try:
            if (
                active is None
                or not active.active
                or active_org is None
                or active_org.status != "active"
            ):
                raise PermissionError("Access revoked")
            actor = Principal(active.user_id, organization_id, active.role)
            actor.require("repository.scan")
            authorized_repository = repository_access(db, actor, current.repository_id, manage=True)
            if not authorized_repository.enabled:
                raise PermissionError("Repository revoked")
        except Exception:
            current.status, current.lease_until = "cancelled", None
            current.report = {"stage": "cancelled", "progress": 0}
            return True
        if status == "completed":
            records = [
                Finding(
                    organization_id=organization_id,
                    repository_id=repository.id,
                    scan_job_id=current.id,
                    commit_sha=commit,
                    **finding,
                )
                for finding in report["findings"]
            ]
            link_observations(db, organization_id, repository.id, records)
            db.add_all(records)
            current.report = {
                "stage": "completed",
                "progress": 100,
                "completed_steps": ["checkout", *report["completed"]],
                "updated_at": now().isoformat(),
                "completed": report["completed"],
                "finding_count": len(report["findings"]),
            }
            emit(db, p, "repository.scan.completed", current.id)
        else:
            current.report = {
                **report,
                "stage": "retrying" if status == "queued" else "failed",
                "progress": 0,
            }
        current.status = status
        current.lease_until = (
            now() + timedelta(seconds=2**current.attempts) if status == "queued" else None
        )
    return True


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--organization", required=True)
    parser.add_argument("--loop", action="store_true")
    args = parser.parse_args()
    from app.worker_health import run_loop

    run_loop(
        "scan",
        args.organization,
        lambda: run_once(args.organization),
        repeat=args.loop,
        interval=5,
        idle_only=True,
    )
