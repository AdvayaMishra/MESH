"""Opt-in actual Redis lease + ASGI SSE acceptance; synthetic identity only.

Starts a temporary password-protected loopback Redis and in-memory SQLite. Never
reads hosted .env or calls Supabase/GitHub. No Windows service is installed.
"""

import argparse
import json
import os
import secrets
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from uuid import uuid4

from redis import Redis
from redis.exceptions import RedisError

ROOT = Path(__file__).resolve().parents[1]


def verify(executable: Path, workspace: Path):
    if not executable.is_absolute() or not executable.is_file() or not workspace.is_absolute():
        raise ValueError("Absolute trusted Redis executable and workspace required")
    checks = {}
    original_cwd = Path.cwd()
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    password = secrets.token_urlsafe(32)
    url = f"redis://:{password}@127.0.0.1:{port}/0"
    process = None
    with tempfile.TemporaryDirectory(prefix="mesh-stream-", dir=workspace) as directory:
        work = Path(directory)
        (work / "redis.conf").write_text(
            f'bind 127.0.0.1\nport {port}\nprotected-mode yes\nrequirepass {password}\nsave ""\nappendonly no\nmaxmemory 32mb\nmaxmemory-policy noeviction\n',
            encoding="utf-8",
        )
        try:
            process = subprocess.Popen(
                [str(executable), "redis.conf"],
                cwd=work,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            redis = Redis.from_url(url, socket_timeout=2, socket_connect_timeout=2)
            for _ in range(50):
                try:
                    if redis.ping():
                        break
                except RedisError:
                    time.sleep(0.1)
            else:
                raise RuntimeError("Disposable Redis did not start")
            checks["actual_password_protected_loopback_redis"] = "passed"
            os.chdir(work)
            sys.path.insert(0, str(ROOT / "backend"))
            from app.core.config import Settings, settings

            # Do not let operator-exported backend settings enter this fixture.
            for field in Settings.model_fields:
                os.environ.pop(field.upper(), None)
            os.environ.update(
                TEST_MODE="true",
                DATABASE_URL="sqlite://",
                REDIS_URL=url,
                AUTH_RATE_SECRET=secrets.token_urlsafe(48),
            )
            settings.cache_clear()
            from app.auth import Identity, Principal, identity
            from app.core.db import Base, SessionFactory
            from app.main import app
            from app.models import Membership, Organization, Repository, ScanJob
            from app.scan_stream import StreamLease
            from fastapi import HTTPException
            from fastapi.testclient import TestClient
            from sqlalchemy import create_engine, event
            from sqlalchemy.orm import Session
            from sqlalchemy.pool import StaticPool

            engine = create_engine(
                "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
            )
            SessionFactory.configure(bind=engine)

            @event.listens_for(engine, "connect")
            def enforce_foreign_keys(connection, _):
                connection.execute("PRAGMA foreign_keys=ON")

            Base.metadata.create_all(engine)
            org, user, repository, job = [str(uuid4()) for _ in range(4)]
            with Session(engine) as db:
                db.add(Organization(id=org, name="Synthetic stream fixture"))
                db.flush()
                db.add(
                    Membership(
                        organization_id=org,
                        user_id=user,
                        email="fixture@example.invalid",
                        role="security_analyst",
                    )
                )
                db.add(
                    Repository(
                        id=repository,
                        organization_id=org,
                        full_name="fixture/stream",
                        installation_id=1,
                        enabled=True,
                    )
                )
                db.flush()
                db.add(
                    ScanJob(
                        id=job,
                        organization_id=org,
                        repository_id=repository,
                        requested_by=user,
                        request_key=uuid4().hex,
                        commit_sha="a" * 40,
                        status="completed",
                        report={"stage": "completed", "progress": 100},
                    )
                )
                db.commit()
            p = Principal(user, org, "security_analyst")
            first, second = StreamLease(p), StreamLease(p)
            first.claim()
            try:
                second.claim()
            except HTTPException as error:
                assert error.status_code == 429
            else:
                raise AssertionError("Concurrent stream was allowed")
            checks["actual_redis_single_member_stream_admission"] = "passed"
            redis.delete(first.key)  # Only this generated fixture's key, never a shared flush.
            successor = StreamLease(p)
            successor.claim()
            first.release()
            assert redis.get(successor.key).decode() == successor.token
            successor.release()
            checks["stale_release_preserves_successor_and_current_release_deletes_lease"] = "passed"
            app.dependency_overrides[identity] = lambda: Identity(
                user, "fixture@example.invalid", "aal2"
            )
            with TestClient(app, raise_server_exceptions=False) as client:
                response = client.get(
                    f"/api/v1/scans/{job}/events", headers={"X-Organization-ID": org}
                )
                assert (
                    response.status_code == 200
                    and "event: scan" in response.text
                    and '"progress":100' in response.text
                )
                assert not redis.exists(f"mesh:scan-stream:{org}:{user}")
                checks["actual_asgi_terminal_snapshot_and_redis_lease_cleanup"] = "passed"
                process.terminate()
                process.wait(timeout=15)
                response = client.get(
                    f"/api/v1/scans/{job}/events", headers={"X-Organization-ID": org}
                )
                assert response.status_code == 503
                checks["redis_outage_denies_stream_before_headers"] = "passed"
            app.dependency_overrides.clear()
            redis.close()
            engine.dispose()
        finally:
            if process is not None and process.poll() is None:
                process.terminate()
                process.wait(timeout=15)
            os.chdir(original_cwd)
    checks["temporary_process_database_and_configuration_removed"] = "passed"
    return {
        "passed": True,
        "checks": checks,
        "limitations": [
            "Real Redis and in-process ASGI streaming; not network HTTP or actual Supabase authentication.",
            "Synthetic test identity and in-memory database; authorization revocation and expiry are covered separately by regression tests.",
        ],
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--redis-executable", type=Path, required=True)
    parser.add_argument("--workspace", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = verify(args.redis_executable, args.workspace)
    except Exception as error:
        report = {"passed": False, "error_type": type(error).__name__}
    (ROOT / "docs/scan-stream-live-results.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, indent=2))
    raise SystemExit(0 if report["passed"] else 1)
