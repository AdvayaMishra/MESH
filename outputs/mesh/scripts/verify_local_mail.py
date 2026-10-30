"""Real Mailpit SMTP + hosted outbox verification; all database fixtures roll back.

Run only against an operator-approved backend database. Starts a loopback-only,
temporary Mailpit process and never relays mail to an external SMTP server.
"""

import argparse
import hashlib
import json
import os
import secrets
import socket
import subprocess
import sys
import time
from datetime import timedelta
from pathlib import Path

import httpx
from cryptography.fernet import Fernet
from dotenv import load_dotenv
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

ROOT = Path(__file__).resolve().parents[1]


def verify(executable: Path) -> dict:
    load_dotenv(ROOT / ".env")
    os.environ.update(
        SMTP_HOST="127.0.0.1",
        SMTP_PORT="11025",
        SMTP_STARTTLS="false",
        SMTP_USERNAME="",
        SMTP_PASSWORD="",
        MAIL_ENCRYPTION_KEY=Fernet.generate_key().decode(),
    )
    sys.path.insert(0, str(ROOT / "backend"))
    from app.core.config import settings
    from app.core.db import assert_runtime_role, tenant_context
    from app.mail import queue_invitation
    from app.models import Invitation, Organization, Outbox, identifier, now
    from app.worker import consume

    if not executable.is_absolute() or not executable.is_file():
        raise ValueError("Explicit absolute Mailpit executable path is required")
    process = subprocess.Popen(
        [str(executable), "--listen", "127.0.0.1:18025", "--smtp", "127.0.0.1:11025"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    engine = create_engine(os.environ["DATABASE_URL"])
    checks = {}
    try:
        with httpx.Client(base_url="http://127.0.0.1:18025", timeout=5) as client:
            for _ in range(40):
                if process.poll() is not None:
                    raise RuntimeError("Mailpit exited before readiness")
                try:
                    if client.get("/api/v1/messages").status_code == 200:
                        break
                except httpx.HTTPError:
                    pass
                time.sleep(0.25)
            else:
                raise RuntimeError("Mailpit did not become ready")
            # Refuse a reused mailbox; fixture checks must refer to this process only.
            assert client.get("/api/v1/messages").json()["total"] == 0
            with Session(engine) as db:
                assert_runtime_role(db)
                org, actor = identifier(), identifier()
                tenant_context(db, org, actor)
                db.add(Organization(id=org, name="Rollback-only Mailpit verification"))
                db.flush()
                token = secrets.token_urlsafe(32)
                invitation = Invitation(
                    organization_id=org,
                    email="fixture@mesh.invalid",
                    role="hr",
                    token_hash=hashlib.sha256(token.encode()).hexdigest(),
                    creator_id=actor,
                    expires_at=now() + timedelta(days=1),
                )
                db.add(invitation)
                db.flush()
                queue_invitation(db, invitation, token)
                db.flush()
                row = db.scalar(select(Outbox).where(Outbox.organization_id == org))
                assert token not in json.dumps(row.payload)
                # A bound but non-listening loopback socket forces a real SMTP
                # transport refusal without contacting any external mail service.
                with socket.socket() as unavailable:
                    unavailable.bind(("127.0.0.1", 0))
                    settings().smtp_port = unavailable.getsockname()[1]
                    assert consume(db, org) == 1
                    db.flush()
                    assert row.status == "pending" and row.attempts == 1
                    assert row.available_at > now()
                    assert "ciphertext" in row.payload
                    assert client.get("/api/v1/messages").json()["total"] == 0
                settings().smtp_port = 11025
                row.available_at = now()
                assert consume(db, org) == 1
                db.flush()
                assert row.status == "delivered" and "ciphertext" not in row.payload
                inventory = client.get("/api/v1/messages").json()
                assert inventory["total"] == 1
                message_id = inventory["messages"][0]["ID"]
                body = client.get("/api/v1/message/" + message_id).json()
                assert token in body["Text"] and org in body["Text"]
                assert consume(db, org) == 0
                assert client.get("/api/v1/messages").json()["total"] == 1
                checks = {
                    "real_loopback_smtp_delivery": "passed",
                    "real_smtp_refusal_retains_ciphertext_and_schedules_retry": "passed",
                    "encrypted_outbox_consumed_and_scrubbed": "passed",
                    "replay_does_not_redeliver_in_transaction": "passed",
                    "database_fixtures_rolled_back": "passed",
                }
                db.rollback()
            client.delete("/api/v1/messages").raise_for_status()
    finally:
        engine.dispose()
        process.terminate()
        process.wait(timeout=15)
    return {
        "checks": checks,
        "limitations": [
            "Native Mailpit; Docker image not run.",
            "No external email or Supabase Auth email tested.",
            "Outbox transaction rolls back; crash-after-send duplicates remain possible.",
        ],
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--mailpit-executable", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = verify(args.mailpit_executable)
    except Exception as exc:
        print(json.dumps({"failed": type(exc).__name__}))
        raise SystemExit(1) from None
    (ROOT / "docs/local-mail-results.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
