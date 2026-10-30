"""Real Redis + ASGI AI stream acceptance with fictional identity and local template.

No hosted environment, model endpoint or provider Auth is used. Actual local model
acceptance is separately recorded by verify_ollama_local.py.
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
        raise ValueError("Absolute trusted executable/workspace required")
    original_cwd = Path.cwd()
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    password = secrets.token_urlsafe(32)
    url = f"redis://:{password}@127.0.0.1:{port}/0"
    checks, process, engine, redis = {}, None, None, None
    with tempfile.TemporaryDirectory(prefix="mesh-ai-stream-", dir=workspace) as directory:
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

            for field in Settings.model_fields:
                os.environ.pop(field.upper(), None)
            os.environ.update(
                TEST_MODE="true",
                DATABASE_URL="sqlite://",
                REDIS_URL=url,
                AUTH_RATE_SECRET=secrets.token_urlsafe(48),
            )
            settings.cache_clear()
            from app import ai_stream
            from app.auth import Identity, Principal, identity
            from app.core.db import Base, session
            from app.main import app
            from app.models import AIUsage, Membership, Organization
            from fastapi.testclient import TestClient
            from sqlalchemy import create_engine, event, func, select
            from sqlalchemy.orm import sessionmaker

            engine = create_engine(
                "sqlite:///" + str(work / "stream.sqlite3"),
                connect_args={"check_same_thread": False},
            )

            @event.listens_for(engine, "connect")
            def foreign_keys(connection, _):
                connection.execute("PRAGMA foreign_keys=ON")

            Base.metadata.create_all(engine)
            factory = sessionmaker(engine, expire_on_commit=False)
            ai_stream.SessionFactory = factory
            org, user = str(uuid4()), str(uuid4())
            with factory.begin() as db:
                db.add(Organization(id=org, name="Fictional stream fixture"))
                db.flush()
                db.add(
                    Membership(
                        organization_id=org,
                        user_id=user,
                        email="fixture@example.invalid",
                        role="hr",
                    )
                )

            def transaction():
                with factory.begin() as db:
                    yield db

            app.dependency_overrides[session] = transaction
            app.dependency_overrides[identity] = lambda: Identity(
                user, "fixture@example.invalid", "aal2"
            )
            actor = Principal(user, org, "hr")
            held = ai_stream.AILease(actor)
            held.claim()
            assert 0 < redis.ttl(held.key) <= 60
            assert not redis.exists(f"mesh:scan-stream:{org}:{user}")
            checks["bounded_lease_separate_from_scan_namespace"] = "passed"
            with TestClient(app) as client:
                headers = {"X-Organization-ID": org}
                response = client.post("/api/v1/ai/stream", headers=headers, json={"purpose": "hr"})
                assert response.status_code == 429 and response.headers["retry-after"] == "30"
                checks["actual_concurrent_stream_admission_denied"] = "passed"
                held.release()
                response = client.post("/api/v1/ai/stream", headers=headers, json={"purpose": "hr"})
                assert response.status_code == 200 and response.text.count("event: result") == 1
                assert '"provider":"local-deterministic"' in response.text
                assert not redis.exists(held.key)
                with factory() as db:
                    assert db.scalar(select(func.count()).select_from(AIUsage)) == 1
                checks["actual_asgi_structured_result_usage_commit_and_lease_cleanup"] = "passed"
                first, second = ai_stream.AILease(actor), ai_stream.AILease(actor)
                first.claim()
                redis.delete(first.key)
                second.claim()
                first.release()
                second.check()
                second.release()
                checks["stale_release_cannot_delete_successor_lease"] = "passed"
                process.terminate()
                process.wait(timeout=15)
                response = client.post("/api/v1/ai/stream", headers=headers, json={"purpose": "hr"})
                assert response.status_code == 503 and "event: result" not in response.text
                checks["redis_outage_denied_before_stream_headers"] = "passed"
            app.dependency_overrides.clear()
        finally:
            if process is not None and process.poll() is None:
                process.terminate()
                process.wait(timeout=15)
            if redis:
                redis.close()
            if engine:
                engine.dispose()
            os.chdir(original_cwd)
    checks["generated_process_database_and_configuration_removed"] = "passed"
    return {
        "passed": True,
        "checks": checks,
        "limitations": [
            "Actual Redis/in-process ASGI with fictional authentication; not network HTTP or Supabase Auth.",
            "The deterministic template is used here. Actual local model adapter acceptance is a separate report.",
            "Failed/ambiguous provider charges and hard vendor spending caps remain outside this contract.",
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
    (ROOT / "docs/ai-stream-live-results.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, indent=2))
    raise SystemExit(0 if report["passed"] else 1)
