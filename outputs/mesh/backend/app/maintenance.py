"""Explicit per-tenant retention worker. Never runs against another tenant implicitly."""

import argparse

from app.auth import Principal
from app.core.db import SessionFactory, assert_runtime_role, tenant_context
from app.documents import expire, reconcile_orphans
from app.models import Organization
from app.telemetry_retention import retire


def run_once(
    organization_id: str, *, orphans: bool = False, telemetry: bool = False, documents: bool = True
) -> int:
    with SessionFactory.begin() as db:
        assert_runtime_role(db)
        tenant_context(db, organization_id, "retention-worker")
        organization = db.get(Organization, organization_id)
        if organization is None:
            raise RuntimeError("Retention tenant not found")
        # Retention must continue for suspended tenants as well.
        p = Principal("retention-worker", organization_id, "system")
        count = expire(db, p) if documents else 0
        if orphans:
            reconcile_orphans(db, p, apply=True)
        if telemetry:
            count += retire(db, p)
        return count


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--organization", required=True)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--reconcile-orphans", action="store_true")
    parser.add_argument("--telemetry-only", action="store_true")
    args = parser.parse_args()
    if args.telemetry_only and args.reconcile_orphans:
        parser.error("Telemetry-only maintenance cannot also reconcile documents")
    from app.worker_health import run_loop

    run_loop(
        "retention",
        args.organization,
        lambda: run_once(
            args.organization,
            orphans=args.reconcile_orphans,
            telemetry=args.telemetry_only,
            documents=not args.telemetry_only,
        ),
        repeat=not args.once,
        interval=60,
    )
