import hashlib
from datetime import UTC, timedelta
from statistics import mean, pstdev
from typing import Literal

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import Principal
from app.models import (
    Anomaly,
    DetectionPolicy,
    Incident,
    IncidentEvent,
    SecurityEvent,
    identifier,
    now,
)
from app.schemas import EventInput, EventOutput
from app.services import emit
from app.telemetry_schema import VOLUME_CATEGORIES, EventContext

RULES: dict[str, tuple[str, int, str]] = {
    "session": (
        "revoked_session_activity",
        25,
        "Reported use of a revoked session requires investigation",
    ),
    "device": ("new_device", 15, "Reported new device requires investigation"),
    "file": ("file_volume", 20, "Reported file access volume requires investigation"),
    "repository": (
        "repository_activity",
        25,
        "Reported repository policy or activity requires investigation",
    ),
    "cloud_audit": (
        "cloud_audit_activity",
        30,
        "Reported cloud audit activity requires investigation",
    ),
    "network": ("network_volume", 20, "Reported network activity requires investigation"),
    "behavior": ("behavior_signal", 15, "Reported behavioral signal requires investigation"),
    "authentication": (
        "failed_authentication_burst",
        25,
        "Five or more failed authentication attempts",
    ),
    "api": ("api_volume", 20, "API volume exceeded 1000 operations in one reported observation"),
    "privilege": ("privilege_change", 30, "Privilege change requires investigation"),
    "database": ("database_volume", 20, "Reported database access volume exceeded 500 operations"),
    "download": ("download_volume", 30, "Reported download volume exceeded 100 units"),
    "cloud": ("cloud_configuration", 20, "Cloud configuration change requires investigation"),
}


def detect(event: SecurityEvent, thresholds: dict | None = None) -> tuple[str, int, str] | None:
    thresholds = thresholds or {}
    triggered = {
        "session": thresholds.get("revoked_session", True)
        and event.action == "revoked_session_used"
        and event.result == "success",
        "device": thresholds.get("new_device", True)
        and ((event.context or {}).get("device") or {}).get("new_device") is True,
        "file": event.count > thresholds.get("file", 500),
        "repository": event.count > thresholds.get("repository", 100)
        or (
            thresholds.get("repository_changes", True)
            and event.result == "success"
            and event.action in {"admin_added", "branch_protection_disabled"}
        ),
        "cloud_audit": event.count > thresholds.get("cloud_audit", 100)
        or (
            thresholds.get("cloud_audit_privilege", True)
            and event.result == "success"
            and event.action in {"root_login", "logging_disabled", "admin_policy_attached"}
        ),
        "network": event.count > thresholds.get("network", 100),
        "behavior": event.count > thresholds.get("behavior", 100),
        "authentication": event.result == "failure"
        and event.count >= thresholds.get("authentication", 5),
        "api": event.count > thresholds.get("api", 1000),
        "privilege": event.result == "success",
        "database": event.count > thresholds.get("database", 500),
        "download": event.count > thresholds.get("download", 100),
        "cloud": event.action == "public_storage_enabled",
    }
    if triggered.get(event.category, False):
        rule, weight, _ = RULES[event.category]
        return (
            rule,
            weight,
            f"{rule}: observed count {event.count}; configured policy signal, not proof of malicious activity",
        )
    return None


def ingest(db: Session, p: Principal, data: EventInput, synthetic: bool = False) -> EventOutput:
    if data.occurred_at > now() + timedelta(minutes=5) or data.occurred_at < now() - timedelta(
        days=30
    ):
        raise HTTPException(
            422, "Telemetry must be within the last 30 days and at most five minutes ahead"
        )
    # Tenant row lock serializes ingestion/correlation against authority revocation.
    from app.correlation import authority

    p = authority(db, p, "security.ingest")
    payload = data.model_dump()
    payload["context"] = data.context.model_dump(exclude_none=True)
    previous = db.scalar(
        select(SecurityEvent).where(
            SecurityEvent.organization_id == p.organization_id,
            SecurityEvent.source_id == data.source_id,
        )
    )
    if previous:
        # A source receipt is bound to immutable normalized telemetry. Reusing a
        # receipt for another actor/session/count must never hide the new payload.
        for field, value in payload.items():
            stored = getattr(previous, field)
            if field == "context":
                stored = EventContext.model_validate(stored or {}).model_dump(exclude_none=True)
            if field == "occurred_at":
                # SQLite test storage omits tzinfo; PostgreSQL retains the instant.
                stored = stored.replace(tzinfo=UTC) if stored.tzinfo is None else stored
                stored, value = stored.astimezone(UTC), value.astimezone(UTC)
            if stored != value:
                raise HTTPException(409, "Telemetry source ID is bound to another event")
        if previous.synthetic != synthetic:
            raise HTTPException(409, "Telemetry source ID is bound to another event")
        return EventOutput(event_id=previous.id, duplicate=True, incident_id=None)
    payload["occurred_at"] = data.occurred_at.astimezone(UTC)
    event = SecurityEvent(
        id=identifier(), organization_id=p.organization_id, synthetic=synthetic, **payload
    )
    db.add(event)
    db.flush()
    policy = db.scalar(
        select(DetectionPolicy).where(DetectionPolicy.organization_id == p.organization_id)
    )
    result = detect(event, policy.thresholds if policy else None)
    if result:
        rule, weight, explanation = result
        db.add(
            Anomaly(
                organization_id=p.organization_id,
                event_id=event.id,
                rule=rule,
                weight=weight,
                explanation=explanation,
            )
        )
        db.flush()
        emit(db, p, "security.anomaly.detected", event.id)
    if not synthetic and event.category in VOLUME_CATEGORIES:
        history = db.scalars(
            select(SecurityEvent.count)
            .where(
                SecurityEvent.organization_id == p.organization_id,
                SecurityEvent.actor_id == event.actor_id,
                SecurityEvent.category == event.category,
                SecurityEvent.synthetic.is_(False),
                SecurityEvent.id != event.id,
                SecurityEvent.occurred_at < event.occurred_at,
            )
            .order_by(SecurityEvent.occurred_at.desc(), SecurityEvent.id)
            .limit(100)
        ).all()
        if (
            len(history) >= 20
            and pstdev(history) > 0
            and event.count > mean(history) + 3 * pstdev(history)
        ):
            db.add(
                Anomaly(
                    organization_id=p.organization_id,
                    event_id=event.id,
                    rule="volume_zscore",
                    weight=15,
                    explanation=f"Reported count exceeds three standard deviations across {len(history)} prior observations; statistical evidence only",
                )
            )
            db.flush()
    from app.correlation import effective, snapshot
    from app.correlation import evidence as select_evidence

    correlation_policy, correlation_config = effective(db, p.organization_id)
    correlation_snapshot = snapshot(correlation_policy, correlation_config)
    evidence, correlation_status = select_evidence(db, p.organization_id, event, correlation_config)
    incident_id = None
    if correlation_status == "incomplete":
        emit(db, p, "security.correlation.incomplete", event.id)
    if correlation_status == "matched":
        ids = list(dict.fromkeys(item[0].id for item in evidence))
        fingerprint = hashlib.sha256(
            (correlation_snapshot["digest"] + "|" + "|".join(sorted(ids))).encode()
        ).hexdigest()
        incident = db.scalar(
            select(Incident).where(
                Incident.organization_id == p.organization_id, Incident.fingerprint == fingerprint
            )
        )
        contributions: dict[str, int] = {}
        for source, weight in evidence:
            contributions[source.id] = weight
        if incident is None:
            incident = db.scalar(
                select(Incident)
                .where(
                    Incident.organization_id == p.organization_id,
                    Incident.actor_id == event.actor_id,
                    Incident.synthetic == synthetic,
                    Incident.status.in_(["open", "triaged"]),
                    Incident.correlation_snapshot["digest"].as_string()
                    == correlation_snapshot["digest"],
                    select(IncidentEvent.id)
                    .where(
                        IncidentEvent.organization_id == p.organization_id,
                        IncidentEvent.incident_id == Incident.id,
                        IncidentEvent.event_id.in_(ids),
                    )
                    .exists(),
                )
                .order_by(Incident.created_at, Incident.id)
                .limit(1)
                .with_for_update()
            )
            if (
                incident
                and len(set(incident.event_ids) | set(ids)) > correlation_config.evidence_limit
            ):
                incident = None
            if incident:
                incident.event_ids = list(dict.fromkeys([*incident.event_ids, *ids]))
                incident.risk = max(incident.risk, min(100, sum(contributions.values())))
        if incident is None:
            # One contribution per event, even if future detectors attach several rules.
            incident = Incident(
                id=identifier(),
                organization_id=p.organization_id,
                actor_id=event.actor_id,
                fingerprint=fingerprint,
                event_ids=ids,
                risk=min(100, sum(contributions.values())),
                explanation=f"At least {correlation_config.minimum_categories} signal categories and {correlation_config.minimum_events} events for the same actor within {correlation_config.window_minutes} minutes, using {correlation_config.link_mode} links and correlation policy version {correlation_snapshot['policy_version']}. Shared identity and timing suggest investigation; routine administration or test activity may explain this sequence. Risk is a policy score, not a probability.",
                synthetic=synthetic,
                correlation_policy_id=correlation_policy.id if correlation_policy else None,
                correlation_snapshot=correlation_snapshot,
            )
            db.add(incident)
            db.flush()
            emit(db, p, "security.incident.created", incident.id)
        existing_ids = set(
            db.scalars(
                select(IncidentEvent.event_id).where(
                    IncidentEvent.organization_id == p.organization_id,
                    IncidentEvent.incident_id == incident.id,
                )
            ).all()
        )
        for related_id in incident.event_ids:
            if related_id not in existing_ids:
                db.add(
                    IncidentEvent(
                        organization_id=p.organization_id,
                        incident_id=incident.id,
                        event_id=related_id,
                    )
                )
        incident_id = incident.id
    emit(db, p, "security.event.ingested", event.id)
    return EventOutput(
        event_id=event.id,
        duplicate=False,
        incident_id=incident_id,
        correlation_status=correlation_status,
    )


def simulate(db: Session, p: Principal, run_id: str) -> list[EventOutput]:
    timestamp = now() - timedelta(minutes=3)
    original = db.scalar(
        select(SecurityEvent).where(
            SecurityEvent.organization_id == p.organization_id,
            SecurityEvent.source_id == f"simulation:{run_id}:0",
        )
    )
    if original is not None:
        timestamp = original.occurred_at
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=UTC)
    scenario: list[
        tuple[
            Literal["authentication", "privilege", "download"],
            str,
            Literal["success", "failure"],
            int,
        ]
    ] = [
        ("authentication", "login", "failure", 8),
        ("privilege", "role_granted", "success", 1),
        ("download", "files_downloaded", "success", 200),
    ]
    return [
        ingest(
            db,
            p,
            EventInput(
                source_id=f"simulation:{run_id}:{index}",
                occurred_at=timestamp + timedelta(minutes=index),
                actor_id=f"synthetic:{run_id}",
                category=category,
                action=action,
                result=result,
                count=count,
            ),
            synthetic=True,
        )
        for index, (category, action, result, count) in enumerate(scenario)
    ]
