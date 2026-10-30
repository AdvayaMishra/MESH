"""Deterministic, versioned policy risk; unknown dimensions are never scored as zero."""

from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import TypedDict

from fastapi import HTTPException
from sqlalchemy import case, func, select

from app.finding_states import UNRESOLVED_FINDING_STATES
from app.models import Anomaly, CloudAssessment, Finding, SecurityEvent

ALGORITHM = "mesh-risk-v1"
DIMENSIONS = (
    "identity",
    "behavior",
    "network",
    "api",
    "privilege",
    "data_access",
    "cloud_posture",
    "code_security",
)
DEFAULT_WEIGHTS = dict(zip(DIMENSIONS, (15, 15, 10, 10, 15, 15, 10, 10), strict=True))
DEFAULT_THRESHOLDS = {"medium": 25, "high": 50, "critical": 75}
SEVERITY = {"info": 10, "low": 25, "medium": 50, "high": 75, "critical": 100}
EVENT_DIMENSION = {
    "session": "identity",
    "device": "behavior",
    "file": "data_access",
    "repository": "code_security",
    "cloud_audit": "cloud_posture",
    "authentication": "identity",
    "behavior": "behavior",
    "network": "network",
    "api": "api",
    "privilege": "privilege",
    "database": "data_access",
    "download": "data_access",
    "cloud": "cloud_posture",
}


class Component(TypedDict):
    score: int | None
    sources: list[str]
    evidence_ids: list[str]
    evidence_count: int
    evidence_truncated: bool


def calculate(scores: dict, weights: dict, thresholds: dict) -> dict:
    if set(scores) != set(DIMENSIONS) or set(weights) != set(DIMENSIONS):
        raise ValueError("All risk dimensions must be explicit")
    if (
        any(type(weight) is not int or not 0 <= weight <= 100 for weight in weights.values())
        or sum(weights.values()) != 100
    ):
        raise ValueError("Risk weights must be integers summing to 100")
    if (
        set(thresholds) != {"medium", "high", "critical"}
        or any(type(value) is not int for value in thresholds.values())
        or not 0 < thresholds["medium"] < thresholds["high"] < thresholds["critical"] < 100
    ):
        raise ValueError("Risk thresholds must be strictly ordered inside 0..100")
    if any(
        value is not None and (type(value) is not int or not 0 <= value <= 100)
        for value in scores.values()
    ):
        raise ValueError("Risk components must be integer scores in 0..100 or unknown")
    coverage = sum(weights[key] for key, value in scores.items() if value is not None)
    numerator = sum(
        Decimal(scores[key]) * weights[key] for key in DIMENSIONS if scores[key] is not None
    )
    lower = numerator / 100
    upper = lower + 100 - coverage
    score = (
        (numerator / coverage).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        if coverage
        else None
    )
    classification = (
        "unassessed"
        if score is None
        else next(
            (name for name in ("critical", "high", "medium") if score >= thresholds[name]), "low"
        )
    )
    return {
        "overall_score": float(score) if score is not None else None,
        "classification": classification,
        "classification_provisional": coverage < 100,
        "coverage_weight": coverage,
        "partial": coverage < 100,
        "missing_dimension_lower_bound": float(lower),
        "missing_dimension_upper_bound": float(upper),
        "calibrated_probability": False,
    }


def collect(db, organization: str, start: datetime, end: datetime, synthetic: bool) -> dict:
    components: dict[str, Component] = {
        key: {
            "score": None,
            "sources": [],
            "evidence_ids": [],
            "evidence_count": 0,
            "evidence_truncated": False,
        }
        for key in DIMENSIONS
    }

    def signal(dimension, score, source, evidence):
        item = components[dimension]
        item["score"] = max(item["score"] or 0, score)
        if source not in item["sources"]:
            item["sources"].append(source)
        item["evidence_count"] += 1
        if len(item["evidence_ids"]) < 1000:
            item["evidence_ids"].append(evidence)

    events = (
        select(SecurityEvent.id, SecurityEvent.category)
        .where(
            SecurityEvent.organization_id == organization,
            SecurityEvent.synthetic == synthetic,
            SecurityEvent.occurred_at >= start,
            SecurityEvent.occurred_at <= end,
        )
        .order_by(SecurityEvent.occurred_at, SecurityEvent.id)
        .limit(10001)
        .subquery()
    )
    rows = db.execute(
        select(
            events.c.id,
            events.c.category,
            func.coalesce(func.max(Anomaly.weight), 0),
            func.max(case((Anomaly.rule == "volume_zscore", 1), else_=0)),
        )
        .outerjoin(
            Anomaly,
            (Anomaly.organization_id == organization) & (Anomaly.event_id == events.c.id),
        )
        .group_by(events.c.id, events.c.category)
        .order_by(events.c.id)
    ).all()
    if len(rows) > 10000:
        raise HTTPException(503, "Risk telemetry exceeds assessment limit; use a shorter window")
    for event_id, category, weight, statistical in rows:
        # A statistical detector takes ownership of its event's contribution;
        # the same event never also contributes to API/data-access dimensions.
        dimension = "behavior" if statistical else EVENT_DIMENSION.get(category)
        if dimension:
            signal(dimension, min(100, max(0, int(weight)) * 2), "telemetry", event_id)
    if not synthetic:
        cloud = db.scalar(
            select(CloudAssessment)
            .where(
                CloudAssessment.organization_id == organization,
                CloudAssessment.created_at >= start,
                CloudAssessment.created_at <= end,
            )
            .order_by(CloudAssessment.created_at.desc(), CloudAssessment.id)
            .limit(1)
        )
        if (
            cloud is not None
            and not cloud.partial
            and all(item.get("severity") in SEVERITY for item in cloud.findings)
        ):
            signal(
                "cloud_posture",
                max((SEVERITY[item["severity"]] for item in cloud.findings), default=0),
                "nonpartial_cloud_assessment",
                cloud.id,
            )
        findings = db.scalars(
            select(Finding)
            .where(
                Finding.organization_id == organization,
                Finding.status.in_(UNRESOLVED_FINDING_STATES),
                Finding.created_at <= end,
            )
            .order_by(Finding.id)
            .limit(10001)
        ).all()
        if len(findings) > 10000:
            raise HTTPException(503, "Risk finding inventory exceeds assessment limit")
        for finding in findings:
            if finding.severity not in SEVERITY:
                raise HTTPException(503, "Risk finding severity is not supported")
            signal("code_security", SEVERITY[finding.severity], "unresolved_finding", finding.id)
    for item in components.values():
        item["evidence_truncated"] = item["evidence_count"] > len(item["evidence_ids"])
    return components
