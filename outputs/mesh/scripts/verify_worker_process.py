"""Committed outbox acceptance using a separate worker process and native Mailpit.

Only a uniquely marked synthetic organization/invitation/outbox/receipt is created.
Those rows are removed in dependency order; audit/history controls are untouched.
"""

import argparse
import hashlib
import json
import os
import secrets
import subprocess
import sys
import time
from datetime import timedelta
from pathlib import Path
from uuid import uuid4

import httpx
from cryptography.fernet import Fernet
from dotenv import dotenv_values
from sqlalchemy import create_engine, delete, func, select
from sqlalchemy.engine import URL
from sqlalchemy.orm import Session

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))


def verify(executable):
    config = {k: v for k, v in dotenv_values(ROOT / ".env").items() if v is not None}
    setup = dotenv_values(
        os.getenv("MESH_SUPABASE_SETUP_FILE", str(ROOT.parents[1] / "work/supabase-setup.env"))
    )
    key = Fernet.generate_key().decode()
    environment = {
        **os.environ,
        **config,
        "PYTHONPATH": str(ROOT / "backend"),
        "SMTP_HOST": "127.0.0.1",
        "SMTP_PORT": "11025",
        "SMTP_STARTTLS": "false",
        "MAIL_ENCRYPTION_KEY": key,
        "TEST_MODE": "false",
    }
    os.environ.update(environment)
    from app.core.config import settings
    from app.core.db import tenant_context
    from app.mail import queue_invitation
    from app.models import Delivery, Invitation, Organization, Outbox, identifier, now

    settings.cache_clear()
    admin_url = URL.create(
        "postgresql+psycopg",
        username="postgres." + setup["SUPABASE_PROJECT_REF"],
        password=setup["SUPABASE_DB_PASSWORD"],
        host=setup["SUPABASE_DB_HOST"],
        port=5432,
        database="postgres",
        query={
            "sslmode": "verify-full",
            "sslrootcert": str(ROOT / "supabase/supabase-ca.crt"),
            "connect_timeout": "15",
        },
    )
    admin = create_engine(admin_url)
    runtime = create_engine(config["DATABASE_URL"])
    org = identifier()
    name = "MESH committed worker fixture " + org
    ledger = ROOT.parents[1] / "work/worker-fixture.json"
    assert not ledger.exists(), "An unresolved worker fixture requires review before rerunning"
    ledger.write_text(
        json.dumps({"organization_id": org, "organization_name": name}), encoding="utf-8"
    )
    process = None
    created = False
    checks = {}
    report = {"checks": checks}
    stage = "mailpit_start"
    try:
        process = subprocess.Popen(
            [str(executable), "--listen", "127.0.0.1:18025", "--smtp", "127.0.0.1:11025"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        with httpx.Client(base_url="http://127.0.0.1:18025", timeout=5) as client:
            for _ in range(40):
                if process.poll() is not None:
                    raise RuntimeError("Mailpit exited")
                try:
                    if client.get("/api/v1/messages").status_code == 200:
                        break
                except httpx.HTTPError:
                    pass
                time.sleep(0.25)
            else:
                raise RuntimeError("Mailpit timeout")
            assert client.get("/api/v1/messages").json()["total"] == 0
            stage = "create_synthetic_parent"
            with Session(admin) as db:
                db.add(Organization(id=org, name=name))
                db.commit()
            created = True
            token = secrets.token_urlsafe(32)
            stage = "commit_encrypted_outbox"
            with Session(runtime) as db:
                tenant_context(db, org, "verification-fixture")
                invitation = Invitation(
                    organization_id=org,
                    email="worker-fixture@mesh.invalid",
                    role="hr",
                    creator_id=str(uuid4()),
                    token_hash=hashlib.sha256(token.encode()).hexdigest(),
                    expires_at=now() + timedelta(days=1),
                )
                db.add(invitation)
                db.flush()
                queue_invitation(db, invitation, token)
                db.flush()
                invitation_id = invitation.id
                db.commit()
            stage = "separate_worker_process"
            completed = subprocess.run(
                [sys.executable, "-m", "app.worker", "--organization", org, "--once"],
                cwd=ROOT,
                env=environment,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=45,
            )
            assert completed.returncode == 0
            with Session(admin) as db:
                row = db.scalar(select(Outbox).where(Outbox.organization_id == org))
                assert row.status == "delivered" and row.payload == {"invitation_id": invitation_id}
                assert (
                    db.scalar(
                        select(func.count())
                        .select_from(Delivery)
                        .where(Delivery.organization_id == org)
                    )
                    == 1
                )
            inventory = client.get("/api/v1/messages").json()
            assert inventory["total"] == 1
            body = client.get("/api/v1/message/" + inventory["messages"][0]["ID"]).json()
            assert token in body["Text"] and org in body["Text"]
            checks["separate_worker_commits_real_smtp_delivery_and_receipt"] = "passed"
            stage = "replay_worker_process"
            replay = subprocess.run(
                [sys.executable, "-m", "app.worker", "--organization", org, "--once"],
                cwd=ROOT,
                env=environment,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=45,
            )
            assert replay.returncode == 0
            with Session(admin) as db:
                assert (
                    db.scalar(
                        select(func.count())
                        .select_from(Delivery)
                        .where(Delivery.organization_id == org)
                    )
                    == 1
                )
            assert client.get("/api/v1/messages").json()["total"] == 1
            checks["separate_worker_replay_does_not_duplicate_committed_receipt"] = "passed"
            client.delete("/api/v1/messages").raise_for_status()
    except Exception as exc:
        report["failure"] = {"stage": stage, "type": type(exc).__name__}
    finally:
        if process and process.poll() is None:
            process.terminate()
            process.wait(timeout=15)
        try:
            if created:
                with Session(admin) as db:
                    parent = db.get(Organization, org)
                    assert parent and parent.name == name
                    for model in (Delivery, Outbox, Invitation):
                        db.execute(delete(model).where(model.organization_id == org))
                    db.execute(
                        delete(Organization).where(
                            Organization.id == org, Organization.name == name
                        )
                    )
                    db.commit()
                with Session(admin) as db:
                    assert db.get(Organization, org) is None
            checks["all_committed_synthetic_rows_removed_without_changing_audit_controls"] = (
                "passed"
            )
            ledger.unlink()
        except Exception:
            report["cleanup_failed"] = True
        runtime.dispose()
        admin.dispose()
    report["passed"] = "failure" not in report and not report.get("cleanup_failed")
    report["limitations"] = [
        "Loopback native Mailpit only; external SMTP/provider email not verified.",
        "Successful committed replay tested; SMTP delivery remains at least once across crash-after-send windows.",
        "No Docker worker image exercised.",
    ]
    (ROOT / "docs/worker-process-results.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--mailpit-executable", type=Path, required=True)
    args = parser.parse_args()
    assert args.mailpit_executable.is_absolute() and args.mailpit_executable.is_file()
    try:
        report = verify(args.mailpit_executable)
    except Exception as exc:
        print(json.dumps({"failed": type(exc).__name__}))
        raise SystemExit(1) from None
    print(json.dumps(report, indent=2))
    raise SystemExit(0 if report["passed"] else 1)
