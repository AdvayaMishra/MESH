"""Rollback-only proof of the narrow PostgreSQL telemetry retirement function."""

import json
import os
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
sys.path.insert(0, str(ROOT / "backend"))

from app.auth import Principal  # noqa: E402
from app.core.config import settings  # noqa: E402
from app.core.db import assert_runtime_role, tenant_context  # noqa: E402
from app.models import (  # noqa: E402
    Anomaly,
    Incident,
    IncidentEvent,
    Membership,
    Organization,
    RiskAssessment,
    RiskPolicy,
    SecurityEvent,
    identifier,
)
from app.services import verify_audit  # noqa: E402
from app.telemetry_retention import retire  # noqa: E402


def verify():
    engine = create_engine(os.environ["DATABASE_URL"])
    org_a, org_b, actor = identifier(), identifier(), identifier()
    original = settings().telemetry_retention_days
    settings().telemetry_retention_days = {org_a: 90}
    checks = {}
    try:
        with Session(engine) as db:
            assert_runtime_role(db)
            server_now = db.scalar(text("SELECT now()"))
            events = []
            for org in (org_a, org_b):
                tenant_context(db, org, actor)
                db.add(Organization(id=org, name="Rollback-only retention verification"))
                db.flush()
                for index in range(4 if org == org_a else 1):
                    record = SecurityEvent(
                        id=identifier(),
                        organization_id=org,
                        source_id=identifier(),
                        occurred_at=server_now - timedelta(days=120) if index != 3 else server_now,
                        actor_id=actor,
                        category="api",
                        action="fixture",
                        result="success",
                        count=1,
                        synthetic=True,
                    )
                    db.add(record)
                    events.append(record)
                db.flush()
            tenant_context(db, org_a, actor)
            retired, linked, legacy, recent, foreign = events
            db.add(
                Membership(
                    organization_id=org_a,
                    user_id=actor,
                    email="risk-retention@example.invalid",
                    role="owner",
                )
            )
            db.flush()
            policy = RiskPolicy(
                organization_id=org_a,
                version=1,
                created_by=actor,
                algorithm_version="retention-fixture",
                weights={},
                thresholds={},
            )
            db.add(policy)
            db.flush()
            protected = SecurityEvent(
                organization_id=org_a,
                source_id=identifier(),
                occurred_at=server_now - timedelta(days=100),
                actor_id=actor,
                category="api",
                action="risk-retention-fixture",
                result="success",
                count=1,
                synthetic=True,
            )
            db.add(protected)
            db.add(
                RiskAssessment(
                    organization_id=org_a,
                    policy_id=policy.id,
                    requested_by=actor,
                    request_key=identifier(),
                    request_digest="0" * 64,
                    window_start=server_now - timedelta(days=101),
                    window_end=server_now - timedelta(days=99),
                    synthetic=True,
                    result={},
                )
            )
            db.flush()
            db.add(
                Anomaly(
                    organization_id=org_a,
                    event_id=retired.id,
                    rule="fixture",
                    weight=1,
                    explanation="Synthetic",
                )
            )
            for record in (linked, legacy):
                incident = Incident(
                    id=identifier(),
                    organization_id=org_a,
                    actor_id=actor,
                    fingerprint=identifier(),
                    event_ids=[record.id],
                    risk=1,
                    explanation="Retained evidence fixture",
                    status="resolved",
                    synthetic=True,
                )
                db.add(incident)
                db.flush()
                if record.id == linked.id:
                    db.add(
                        IncidentEvent(
                            organization_id=org_a, incident_id=incident.id, event_id=record.id
                        )
                    )
            db.flush()
            assert retire(db, Principal("retention-worker", org_a, "system")) == 1
            remaining = set(db.scalars(select(SecurityEvent.id)).all())
            assert retired.id not in remaining
            assert {linked.id, legacy.id, recent.id} <= remaining
            assert db.scalar(select(Anomaly.id).where(Anomaly.event_id == retired.id)) is None
            checks["old_uncorrelated_event_and_child_anomaly_retired"] = "passed"
            checks["recent_relational_and_legacy_json_incident_evidence_preserved"] = "passed"
            tenant_context(db, org_b, actor)
            assert (
                db.scalar(select(SecurityEvent.id).where(SecurityEvent.id == foreign.id))
                == foreign.id
            )
            checks["other_tenant_event_is_untouched"] = "passed"
            tenant_context(db, org_a, actor)
            try:
                with db.begin_nested():
                    db.execute(text("DELETE FROM security_events WHERE id=:id"), {"id": recent.id})
            except DBAPIError as exc:
                assert exc.orig.sqlstate == "42501"
            else:
                raise AssertionError("Runtime unexpectedly has direct telemetry DELETE privileges")
            checks["runtime_has_no_direct_delete_privilege"] = "passed"
            tenant_context(db, "", actor)
            try:
                with db.begin_nested():
                    db.scalar(text("SELECT public.mesh_retire_telemetry(90,250)"))
            except DBAPIError as exc:
                assert exc.orig.sqlstate == "P0001"
            else:
                raise AssertionError("Retention accepted an absent tenant context")
            checks["missing_tenant_context_is_rejected"] = "passed"
            tenant_context(db, org_a, actor)
            assert verify_audit(db, Principal(actor, org_a, "system"))["valid"]
            assert (
                db.scalar(select(SecurityEvent.id).where(SecurityEvent.id == protected.id))
                == protected.id
            )
            checks["risk_assessment_window_evidence_preserved"] = "passed"
            checks["retirement_audit_hash_valid"] = "passed"
            db.rollback()
            tenant_context(db, org_a, actor)
            assert db.scalar(select(Organization).where(Organization.id == org_a)) is None
            checks["all_synthetic_changes_rolled_back"] = "passed"
    finally:
        settings().telemetry_retention_days = original
        engine.dispose()
    return {
        "verified_at_utc": datetime.now(UTC).isoformat(),
        "checks": checks,
        "limitations": [
            "Only uncorrelated raw telemetry/anomalies are eligible; incident evidence, risk-assessment windows and audit ledgers are retained.",
            "No real customer telemetry or external object was deleted.",
        ],
    }


if __name__ == "__main__":
    try:
        report = verify()
    except Exception as exc:
        print(json.dumps({"failed": type(exc).__name__}))
        raise SystemExit(1) from None
    (ROOT / "docs/telemetry-retention-results.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, indent=2))
