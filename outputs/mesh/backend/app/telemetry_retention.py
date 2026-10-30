from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.auth import Principal
from app.core.config import settings
from app.models import Outbox
from app.services import audit


def retire(db: Session, p: Principal, batch_size: int = 250) -> int:
    days = settings().telemetry_retention_days.get(p.organization_id)
    if days is None:
        raise HTTPException(503, "No operator-approved telemetry retention policy is configured")
    if not 30 <= days <= 3650 or not 1 <= batch_size <= 1000:
        raise HTTPException(422, "Invalid retention bounds")
    if db.get_bind().dialect.name != "postgresql":
        raise HTTPException(503, "Telemetry retirement requires PostgreSQL enforcement")
    db.execute(text("SET LOCAL statement_timeout='10s'"))
    count = db.scalar(
        text("SELECT public.mesh_retire_telemetry(:days,:batch)"),
        {"days": days, "batch": batch_size},
    )
    if count:
        audit(db, p, "security.telemetry.retired", p.organization_id)
        db.add(
            Outbox(
                organization_id=p.organization_id,
                topic="security.telemetry.retired",
                payload={
                    "target_id": p.organization_id,
                    "version": 1,
                    "removed_events": count,
                    "retention_days": days,
                },
            )
        )
    return int(count or 0)
