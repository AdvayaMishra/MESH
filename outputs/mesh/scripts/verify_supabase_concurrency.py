"""Concurrent audit-lock validation using one temporary, synthetic organization.

Only the synthetic parent is committed. Both workers roll back all ledger/outbox
writes; finally, the script deletes only its uniquely identified parent record.
"""

import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from threading import Barrier

from dotenv import dotenv_values, load_dotenv
from sqlalchemy import create_engine, delete
from sqlalchemy.engine import URL
from sqlalchemy.orm import Session

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
sys.path.insert(0, str(ROOT / "backend"))

from app.auth import Principal  # noqa: E402
from app.core.db import tenant_context  # noqa: E402
from app.models import Organization, Outbox, identifier  # noqa: E402
from app.services import audit, verify_audit  # noqa: E402


def verify():
    setup_path = Path(
        os.getenv("MESH_SUPABASE_SETUP_FILE", str(ROOT.parents[1] / "work/supabase-setup.env"))
    )
    config = {**dotenv_values(ROOT / ".env"), **dotenv_values(setup_path)}
    admin_url = URL.create(
        "postgresql+psycopg",
        username="postgres." + config["SUPABASE_PROJECT_REF"],
        password=config["SUPABASE_DB_PASSWORD"],
        host=config["SUPABASE_DB_HOST"],
        port=5432,
        database="postgres",
        query={
            "sslmode": "verify-full",
            "sslrootcert": str(ROOT / "supabase/supabase-ca.crt"),
            "connect_timeout": "15",
            "options": "-c statement_timeout=30000 -c lock_timeout=15000",
        },
    )
    admin = create_engine(admin_url)
    runtime = create_engine(os.environ["DATABASE_URL"])
    organization, user = identifier(), identifier()
    name = "MESH concurrency fixture " + organization
    barrier = Barrier(2)

    def append_and_rollback():
        with Session(runtime) as db:
            tenant_context(db, organization, user)
            db.add(Outbox(organization_id=organization, topic="verification.fixture", payload={}))
            db.flush()
            barrier.wait(timeout=20)
            principal = Principal(user, organization, "junior_developer")
            audit(db, principal, "verification.concurrent", organization)
            result = verify_audit(db, principal)
            assert result["valid"] and result["sealed_records"] == 1
            db.rollback()

    try:
        with admin.begin() as connection:
            connection.execute(Organization.__table__.insert().values(id=organization, name=name))
        try:
            with ThreadPoolExecutor(max_workers=2) as workers:
                futures = [workers.submit(append_and_rollback) for _ in range(2)]
                for future in futures:
                    future.result(timeout=45)
        finally:
            with admin.begin() as connection:
                result = connection.execute(
                    delete(Organization).where(
                        Organization.id == organization, Organization.name == name
                    )
                )
                assert result.rowcount == 1
    finally:
        runtime.dispose()
        admin.dispose()
    return {
        "project_ref": config["SUPABASE_PROJECT_REF"],
        "verified_at_utc": datetime.now(UTC).isoformat(),
        "concurrent_audit_append_without_deadlock": "passed",
        "audit_hashes_in_each_transaction": "passed",
        "child_writes_rolled_back_and_synthetic_parent_deleted": "passed",
        "limitation": "Rollback-only child writes do not validate a committed multi-writer chain.",
    }


if __name__ == "__main__":
    try:
        report = verify()
    except Exception as exc:
        print(json.dumps({"failed": type(exc).__name__}))
        raise SystemExit(1) from None
    (ROOT / "docs/supabase-concurrency-results.json").write_text(
        json.dumps(report, indent=2) + "\n"
    )
    print(json.dumps(report, indent=2))
