"""Versioned correlation policy and bounded evidence selection."""

import hashlib
import json
from datetime import datetime, timedelta
from typing import Annotated, Literal, get_args

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.auth import Principal
from app.models import Anomaly, CorrelationPolicy, Membership, SecurityEvent
from app.schemas import CorrelationState, Input
from app.services import emit, lock_tenant
from app.telemetry_schema import EventCategory

ALGORITHM = "correlation-v2"


class CorrelationConfig(Input):
    enabled: Annotated[bool, Field(strict=True)] = True
    window_minutes: Annotated[int, Field(strict=True, ge=1, le=1440)] = 30
    minimum_categories: Annotated[int, Field(strict=True, ge=2, le=13)] = 3
    minimum_events: Annotated[int, Field(strict=True, ge=2, le=5000)] = 3
    evidence_limit: Annotated[int, Field(strict=True, ge=3, le=5000)] = 1000
    link_mode: Literal["legacy", "actor", "session", "resource", "session_or_resource"] = "legacy"
    categories: Annotated[list[EventCategory], Field(min_length=2, max_length=13)] = Field(
        default_factory=lambda: list(get_args(EventCategory))
    )

    @model_validator(mode="after")
    def consistent(self):
        if len(set(self.categories)) != len(self.categories):
            raise ValueError("Correlation categories must be unique")
        if not self.minimum_categories <= len(self.categories):
            raise ValueError("Category threshold exceeds configured categories")
        if not self.minimum_categories <= self.minimum_events <= self.evidence_limit:
            raise ValueError("Event threshold must cover category threshold and fit evidence limit")
        self.categories = sorted(self.categories)
        return self


class PolicyChange(Input):
    expected_version: Annotated[int, Field(strict=True, ge=0, le=2147483646)]
    configuration: CorrelationConfig


class PolicyOutput(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str | None
    version: int
    algorithm_version: str
    configuration: CorrelationConfig
    created_by: str | None
    created_at: datetime | None


class PolicyHistory(BaseModel):
    policies: list[PolicyOutput]
    total_policies: int
    limit: int
    offset: int


def effective(db: Session, organization: str) -> tuple[CorrelationPolicy | None, CorrelationConfig]:
    row = db.scalar(
        select(CorrelationPolicy)
        .where(CorrelationPolicy.organization_id == organization)
        .order_by(CorrelationPolicy.version.desc())
        .limit(1)
    )
    if row is None:
        return None, CorrelationConfig()
    try:
        if row.algorithm_version != ALGORITHM:
            raise ValueError("Unknown stored algorithm")
        return row, CorrelationConfig.model_validate(row.configuration)
    except ValueError:
        raise HTTPException(503, "Stored correlation policy requires review") from None


def output(row: CorrelationPolicy | None, config: CorrelationConfig) -> PolicyOutput:
    return PolicyOutput(
        id=row.id if row else None,
        version=row.version if row else 0,
        algorithm_version=row.algorithm_version if row else ALGORITHM,
        configuration=config,
        created_by=row.created_by if row else None,
        created_at=row.created_at if row else None,
    )


def authority(
    db: Session,
    p: Principal,
    permission: Literal["security.read", "security.ingest"] = "security.read",
) -> Principal:
    p.require(permission)
    organization = lock_tenant(db, p.organization_id)
    if organization is not None:
        db.refresh(organization, attribute_names=["status"])
    member = db.get(
        Membership, (p.organization_id, p.user_id), with_for_update=True, populate_existing=True
    )
    if (
        organization is None
        or organization.status != "active"
        or member is None
        or not member.active
    ):
        raise HTTPException(403, "Active security authority required")
    fresh = Principal(member.user_id, p.organization_id, member.role, p.session_id)
    fresh.require(permission)
    return fresh


def create_policy(db: Session, p: Principal, data: PolicyChange) -> PolicyOutput:
    fresh = authority(db, p, "security.ingest")
    previous, _ = effective(db, p.organization_id)
    version = previous.version if previous else 0
    if data.expected_version != version or version >= 2147483647:
        raise HTTPException(409, "Correlation policy changed; fetch the current version")
    row = CorrelationPolicy(
        organization_id=p.organization_id,
        version=version + 1,
        created_by=p.user_id,
        algorithm_version=ALGORITHM,
        configuration=data.configuration.model_dump(mode="json"),
    )
    db.add(row)
    db.flush()
    emit(db, fresh, "security.correlation_policy.created", row.id)
    return output(row, data.configuration)


def snapshot(row: CorrelationPolicy | None, config: CorrelationConfig) -> dict:
    value = {
        "algorithm_version": ALGORITHM,
        "policy_id": row.id if row else None,
        "policy_version": row.version if row else 0,
        "configuration": config.model_dump(mode="json"),
    }
    value["digest"] = hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return value


def evidence(
    db: Session, organization: str, event: SecurityEvent, config: CorrelationConfig
) -> tuple[list[tuple[SecurityEvent, int]], CorrelationState]:
    if not config.enabled:
        return [], "disabled"
    if event.category not in config.categories:
        return [], "excluded"
    latest = db.scalar(
        select(func.max(SecurityEvent.occurred_at)).where(
            SecurityEvent.organization_id == organization,
            SecurityEvent.actor_id == event.actor_id,
            SecurityEvent.synthetic == event.synthetic,
            SecurityEvent.category.in_(config.categories),
        )
    )
    if latest is None:
        raise RuntimeError("Inserted event timestamp missing")
    query = select(SecurityEvent.id).where(
        SecurityEvent.organization_id == organization,
        SecurityEvent.actor_id == event.actor_id,
        SecurityEvent.synthetic == event.synthetic,
        SecurityEvent.category.in_(config.categories),
        SecurityEvent.occurred_at >= latest - timedelta(minutes=config.window_minutes),
        SecurityEvent.occurred_at <= latest,
        select(Anomaly.id)
        .where(Anomaly.organization_id == organization, Anomaly.event_id == SecurityEvent.id)
        .exists(),
    )
    links = []
    if event.session_id:
        links.append(SecurityEvent.session_id == event.session_id)
    if event.resource_id:
        links.append(SecurityEvent.resource_id == event.resource_id)
    if config.link_mode == "session":
        if not event.session_id:
            return [], "insufficient"
        query = query.where(SecurityEvent.session_id == event.session_id)
    elif config.link_mode == "resource":
        if not event.resource_id:
            return [], "insufficient"
        query = query.where(SecurityEvent.resource_id == event.resource_id)
    elif config.link_mode == "session_or_resource" or (
        config.link_mode == "legacy" and event.session_id
    ):
        if not links:
            return [], "insufficient"
        query = query.where(or_(*links))
    eligible = (
        query.order_by(SecurityEvent.occurred_at, SecurityEvent.id)
        .limit(config.evidence_limit + 1)
        .subquery()
    )
    rows = db.execute(
        select(SecurityEvent, func.max(Anomaly.weight))
        .join(eligible, eligible.c.id == SecurityEvent.id)
        .join(
            Anomaly,
            (Anomaly.organization_id == SecurityEvent.organization_id)
            & (Anomaly.event_id == SecurityEvent.id),
        )
        .where(SecurityEvent.organization_id == organization)
        .group_by(SecurityEvent.id)
        .order_by(SecurityEvent.occurred_at, SecurityEvent.id)
    ).all()
    if len(rows) > config.evidence_limit:
        return [], "incomplete"
    selected = [(row[0], int(row[1])) for row in rows]
    if (
        len(selected) < config.minimum_events
        or len({row.category for row, _ in selected}) < config.minimum_categories
        or event.id not in {row.id for row, _ in selected}
    ):
        return selected, "insufficient"
    return selected, "matched"
