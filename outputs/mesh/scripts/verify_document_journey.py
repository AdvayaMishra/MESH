"""Real ASGI authorization + JWT/MFA + Redis + PostgreSQL + ClamAV + private Storage.

Only the DB session dependency is overridden to prevent fixture/audit commits.
All external adapters and authorization remain real. Temporary provider identity
is managed by verify_supabase_provider; object cleanup is independently checked.
"""

import argparse
import io
import json
import secrets
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from uuid import uuid4

import httpx
from dotenv import load_dotenv
from PIL import Image
from redis import Redis
from redis.exceptions import RedisError

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
sys.path.insert(0, str(ROOT / "backend"))
from app.core.config import settings  # noqa: E402


def probe(db, person, tokens, checks):
    from app.core.db import session, tenant_context
    from app.documents import PrivateStorage
    from app.main import app
    from app.models import Employee, Membership, Organization
    from fastapi.testclient import TestClient
    from verify_supabase_provider import storage_object_missing

    org, employee_id, other_id, other_user = [str(uuid4()) for _ in range(4)]
    tenant_context(db, org, person.user_id)
    db.add(Organization(id=org, name="MESH rollback-only document acceptance"))
    db.flush()
    for user in [person.user_id, other_user]:
        db.add(
            Membership(
                organization_id=org, user_id=user, email=user + "@example.invalid", role="hr"
            )
        )
    db.flush()
    for employee, user in [(employee_id, person.user_id), (other_id, other_user)]:
        db.add(
            Employee(
                id=employee,
                organization_id=org,
                user_id=user,
                name="Synthetic PNG fixture",
                department="Fixture",
            )
        )
    db.flush()

    def rollback_session():
        yield db

    app.dependency_overrides[session] = rollback_session
    output = io.BytesIO()
    Image.new("RGB", (4, 4), "white").save(output, "PNG")
    content = output.getvalue()
    headers = {
        "Authorization": "Bearer " + tokens.access_token,
        "X-Organization-ID": org,
        "Content-Type": "image/png",
    }
    storage = PrivateStorage()
    cleanup_keys = []
    ledger = ROOT.parents[1] / "work/document-journey-fixture.json"
    assert not ledger.exists(), "Unresolved document fixture requires cleanup"
    ledger.write_text(json.dumps({"organization_id": org, "keys": cleanup_keys}))
    original_upload = PrivateStorage.upload

    def tracked_upload(adapter, key, data, media_type):
        # Record an attempted external side effect before sending bytes.
        assert key.startswith(org + "/")
        cleanup_keys.append(key)
        ledger.write_text(json.dumps({"organization_id": org, "keys": cleanup_keys}))
        return original_upload(adapter, key, data, media_type)

    PrivateStorage.upload = tracked_upload
    try:
        with TestClient(app) as client:
            denied = client.post(
                f"/api/v1/employees/{other_id}/identity-documents", headers=headers, content=content
            )
            assert denied.status_code == 403
            denied = client.post(
                f"/api/v1/employees/{employee_id}/identity-documents",
                headers={**headers, "X-Organization-ID": str(uuid4())},
                content=content,
            )
            assert denied.status_code == 403
            checks["combined_http_document_owner_and_tenant_denial"] = "passed"
            response = client.post(
                f"/api/v1/employees/{employee_id}/identity-documents",
                headers=headers,
                content=content,
            )
            tenant_context(db, org, person.user_id)
            assert response.status_code == 201, f"Upload returned HTTP {response.status_code}"
            document = response.json()["id"]
            signed = client.get(
                f"/api/v1/hr/identity-documents/{document}/signed-url", headers=headers
            )
            assert signed.status_code == 200
            with httpx.Client(timeout=15, follow_redirects=False) as external:
                downloaded = external.get(signed.json()["url"])
                assert downloaded.status_code == 200 and downloaded.content == content
            checks["combined_http_jwt_mfa_malware_private_upload_sign_download"] = "passed"
            review = client.post(
                f"/api/v1/hr/identity-documents/{document}/decision",
                headers={**headers, "Content-Type": "application/json"},
                json={"decision": "approved"},
            )
            assert review.status_code == 409
            checks["combined_http_independent_hr_review_enforced"] = "passed"
    finally:
        PrivateStorage.upload = original_upload
        app.dependency_overrides.pop(session, None)
        for key in cleanup_keys:
            storage.delete(key)
            config = settings()
            secret = config.supabase_storage_key.get_secret_value()
            service = {"apikey": secret}
            if not secret.startswith("sb_secret_"):
                service["Authorization"] = "Bearer " + secret
            with httpx.Client(timeout=15, follow_redirects=False) as external:
                missing = external.get(
                    config.supabase_url.rstrip("/") + "/storage/v1/object/mesh-identity/" + key,
                    headers=service,
                )
                assert storage_object_missing(missing), "Document fixture cleanup not verified"
        ledger.unlink()
    checks["combined_document_storage_fixture_removed"] = "passed"


def verify(redis_executable, clamd_executable, database):
    for path in [redis_executable, clamd_executable, database]:
        assert path.is_absolute() and path.exists()
    config = settings()
    config.test_mode = False
    config.clamav_host = "127.0.0.1"
    config.clamav_port = 13311
    password = secrets.token_urlsafe(32)
    config.redis_url = f"redis://:{password}@127.0.0.1:16380/0"
    processes = []
    with tempfile.TemporaryDirectory(prefix="mesh-document-services-") as folder:
        work = Path(folder)
        (work / "redis.conf").write_text(
            f'bind 127.0.0.1\nport 16380\nprotected-mode yes\nrequirepass {password}\nsave ""\nappendonly no\nmaxmemory 32mb\n'
        )
        (work / "clamd.conf").write_text(
            f"DatabaseDirectory {database.as_posix()}\nTCPSocket 13311\nTCPAddr 127.0.0.1\nForeground yes\nMaxThreads 2\nMaxQueue 4\nStreamMaxLength 2M\nMaxScanSize 10M\nMaxFileSize 2M\nAlertExceedsMax yes\n"
        )
        try:
            for command in [
                [str(redis_executable), "redis.conf"],
                [str(clamd_executable), "--config-file=" + str(work / "clamd.conf")],
            ]:
                processes.append(
                    subprocess.Popen(
                        command, cwd=work, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                    )
                )
            for _ in range(240):
                if any(p.poll() is not None for p in processes):
                    raise RuntimeError("A fixture service exited")
                try:
                    with Redis.from_url(
                        config.redis_url, socket_connect_timeout=0.5, socket_timeout=1
                    ) as redis:
                        assert redis.ping()
                    with socket.create_connection(("127.0.0.1", 13311), timeout=0.5) as connection:
                        connection.sendall(b"zPING\0")
                        assert connection.recv(64).strip(b"\0\r\n") == b"PONG"
                    break
                except (OSError, AssertionError, RedisError):
                    time.sleep(0.25)
            else:
                raise RuntimeError("Fixture service readiness timed out")
            from verify_supabase_provider import verify as provider_verify

            report = provider_verify(after_mfa=probe)
            report["limitations"] = [
                limitation
                for limitation in report["limitations"]
                if not limitation.startswith(
                    ("Application handlers called directly", "Storage adapter verified separately")
                )
            ]
            report["limitations"].append(
                "ASGI HTTP with real middleware/adapters; only DB session dependency overridden for rollback. Not a separate API process or external inbox/CAPTCHA test."
            )
            return report
        finally:
            for process in processes:
                if process.poll() is None:
                    process.terminate()
                    process.wait(timeout=20)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--redis-executable", type=Path, required=True)
    parser.add_argument("--clamd-executable", type=Path, required=True)
    parser.add_argument("--database-directory", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = verify(args.redis_executable, args.clamd_executable, args.database_directory)
    except Exception as error:
        print(json.dumps({"failed": type(error).__name__}))
        raise SystemExit(1) from None
    (ROOT / "docs/document-journey-results.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result["passed"] else 1)
