from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import case, func, select

from app.ai import Insight, authority, generate
from app.api import DB, Limit, Offset, P
from app.cloud import configured_aws
from app.devtrack import project_access
from app.enterprise_api import FINANCE
from app.finance import summarize
from app.models import (
    AIUsage,
    Anomaly,
    CloudAssessment,
    CostRecord,
    DetectionPolicy,
    Employee,
    Incident,
    IncidentEvent,
    RiskAssessment,
    SecurityEvent,
    Task,
    identifier,
)
from app.schemas import Input
from app.services import audit, emit, lock_tenant, scoped
from app.telemetry_schema import VolumeCategory

router = APIRouter(prefix="/api/v1")


class PolicyInput(Input):
    file: Annotated[int, Field(ge=1, le=1000000)] = 500
    repository: Annotated[int, Field(ge=1, le=1000000)] = 100
    cloud_audit: Annotated[int, Field(ge=1, le=1000000)] = 100
    new_device: Annotated[bool, Field(strict=True)] = True
    revoked_session: Annotated[bool, Field(strict=True)] = True
    repository_changes: Annotated[bool, Field(strict=True)] = True
    cloud_audit_privilege: Annotated[bool, Field(strict=True)] = True
    network: Annotated[int, Field(ge=1, le=1000000)] = 100
    behavior: Annotated[int, Field(ge=1, le=1000000)] = 100
    authentication: Annotated[int, Field(ge=1, le=10000)] = 5
    api: Annotated[int, Field(ge=1, le=1000000)] = 1000
    database: Annotated[int, Field(ge=1, le=1000000)] = 500
    download: Annotated[int, Field(ge=1, le=1000000)] = 100


class IncidentUpdate(Input):
    status: Literal["triaged", "contained", "resolved", "false_positive"]


class InsightOutput(Insight):
    provider: str
    usage: dict
    currency: str | None = None


class CloudOutput(BaseModel):
    id: str
    provider: str = "aws"
    findings: list[dict]
    partial: bool
    errors: list[dict]
    coverage: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


class RiskDimension(BaseModel):
    category: str
    event_count: int
    scored_events: int
    raw_weight: int


class RiskProjection(BaseModel):
    incident_id: str
    stored_score: int
    retained_evidence_score: int
    matches_stored_score: bool
    evidence_complete: bool
    missing_events: int
    dimensions: list[RiskDimension]
    projection_version: Literal["retained-event-weights-v1"] = "retained-event-weights-v1"
    original_model_version: None = None
    calibrated_probability: bool = False
    limitations: list[str]


@router.put("/vader/detection-policy", response_model=PolicyInput)
def policy_set(data: PolicyInput, db: DB, p: P):
    p.require("security.ingest")
    lock_tenant(db, p.organization_id)
    record = db.scalar(
        select(DetectionPolicy)
        .where(DetectionPolicy.organization_id == p.organization_id)
        .with_for_update()
    )
    if record is None:
        record = DetectionPolicy(
            id=identifier(), organization_id=p.organization_id, thresholds=data.model_dump()
        )
        db.add(record)
    else:
        record.thresholds = data.model_dump()
    emit(db, p, "security.policy.updated", record.id)
    return data


@router.get("/vader/baseline/{actor_id}")
def baseline(
    actor_id: UUID,
    db: DB,
    p: P,
    category: VolumeCategory = "api",
) -> dict[str, int | bool | str]:
    p.require("security.read")
    counts = db.scalars(
        select(SecurityEvent.count)
        .where(
            SecurityEvent.organization_id == p.organization_id,
            SecurityEvent.actor_id == str(actor_id),
            SecurityEvent.category == category,
            SecurityEvent.synthetic.is_(False),
        )
        .order_by(SecurityEvent.occurred_at.desc(), SecurityEvent.id)
        .limit(100)
    ).all()
    return {
        "observations": len(counts),
        "cold_start": len(counts) < 20,
        "category": category,
        "method": "per-actor/category mean plus three population standard deviations; last 100 prior observations",
    }


@router.patch("/vader/incidents/{incident_id}")
def incident_update(incident_id: UUID, data: IncidentUpdate, db: DB, p: P) -> dict[str, str]:
    p.require("security.read")
    record = scoped(db, Incident, p, str(incident_id), lock=True)
    transitions = {
        "open": {"triaged", "false_positive"},
        "triaged": {"contained", "resolved", "false_positive"},
        "contained": {"resolved"},
    }
    if data.status not in transitions.get(record.status, set()):
        raise HTTPException(409, "Invalid incident transition")
    record.status = data.status
    emit(db, p, "security.incident." + record.status, record.id)
    return {"id": record.id, "status": record.status}


@router.get("/vader/risk/{incident_id}")
def risk(incident_id: UUID, db: DB, p: P) -> dict:
    p.require("security.read")
    record = scoped(db, Incident, p, str(incident_id))
    return {
        "incident_id": record.id,
        "score": record.risk,
        "calibrated_probability": False,
        "explanation": record.explanation,
        "aggregation": "one maximum rule weight per underlying event; capped at 100",
    }


@router.post("/vader/cloud/assess", response_model=CloudOutput)
def cloud_assess(db: DB, p: P):
    p.require("security.read")
    result = configured_aws(p.organization_id).assess()
    from app.cloud_publication import Report, assessment_record

    record = assessment_record(Report.model_validate(result), p.organization_id)
    db.add(record)
    emit(db, p, "security.cloud.assessed", record.id)
    return cloud_output(record)


@router.get("/vader/incidents/{incident_id}/risk-evidence", response_model=RiskProjection)
def risk_evidence(incident_id: UUID, db: DB, p: P):
    """Versioned projection of retained evidence, not a rewrite of original risk."""
    p.require("security.read")
    record = scoped(db, Incident, p, str(incident_id))
    links = db.scalars(
        select(IncidentEvent.event_id)
        .where(
            IncidentEvent.organization_id == p.organization_id,
            IncidentEvent.incident_id == record.id,
        )
        .limit(10001)
    ).all()
    if len(links) > 10000 or len(record.event_ids) > 10000:
        raise HTTPException(503, "Incident evidence exceeds projection limit")
    expected = set(links) | set(record.event_ids)
    if len(expected) > 10000:
        raise HTTPException(503, "Incident evidence exceeds projection limit")
    # One maximum anomaly weight per event prevents double-counting detectors.
    weights = (
        select(
            SecurityEvent.id,
            SecurityEvent.category,
            func.coalesce(func.max(Anomaly.weight), 0).label("weight"),
        )
        .outerjoin(
            Anomaly,
            (Anomaly.organization_id == SecurityEvent.organization_id)
            & (Anomaly.event_id == SecurityEvent.id),
        )
        .where(
            SecurityEvent.organization_id == p.organization_id,
            SecurityEvent.id.in_(expected),
            SecurityEvent.actor_id == record.actor_id,
            SecurityEvent.synthetic == record.synthetic,
        )
        .group_by(SecurityEvent.id, SecurityEvent.category)
        .subquery()
    )
    dimensions = [
        RiskDimension(
            category=category,
            event_count=int(count),
            scored_events=int(scored),
            raw_weight=int(weight),
        )
        for category, count, scored, weight in db.execute(
            select(
                weights.c.category,
                func.count(),
                func.sum(case((weights.c.weight > 0, 1), else_=0)),
                func.sum(case((weights.c.weight > 0, weights.c.weight), else_=0)),
            )
            .group_by(weights.c.category)
            .order_by(weights.c.category)
        )
    ]
    retained = min(100, sum(item.raw_weight for item in dimensions))
    missing = len(expected) - sum(item.event_count for item in dimensions)
    audit(db, p, "security.incident.risk_evidence.read", record.id)
    return RiskProjection(
        incident_id=record.id,
        stored_score=record.risk,
        retained_evidence_score=retained,
        matches_stored_score=retained == record.risk,
        evidence_complete=missing == 0,
        missing_events=missing,
        dimensions=dimensions,
        limitations=[
            "Current retained anomaly weights only; original detector/policy versions were not stored.",
            "Accumulated incident evidence can differ from the original rolling-window score; stored score is unchanged.",
            "Category weights are policy signals, not calibrated probabilities or proof of malicious activity.",
        ],
    )


def cloud_output(record: CloudAssessment) -> CloudOutput:
    return CloudOutput(
        id=record.id,
        provider=record.provider,
        findings=record.findings,
        partial=record.partial,
        errors=record.errors or [],
        coverage=record.coverage or [],
        limitations=record.limitations
        or ["Legacy assessment has incomplete retained coverage/error metadata"],
    )


@router.get("/vader/cloud/assessments", response_model=list[CloudOutput])
def cloud_history(db: DB, p: P, limit: Limit = 50, offset: Offset = 0):
    p.require("security.read")
    records = db.scalars(
        select(CloudAssessment)
        .where(CloudAssessment.organization_id == p.organization_id)
        .order_by(CloudAssessment.created_at.desc(), CloudAssessment.id)
        .limit(limit)
        .offset(offset)
    ).all()
    audit(db, p, "security.cloud.history_read", p.organization_id)
    return [cloud_output(record) for record in records]


@router.get("/vader/cloud/assessments/{assessment_id}", response_model=CloudOutput)
def cloud_assessment_get(assessment_id: UUID, db: DB, p: P):
    p.require("security.read")
    record = scoped(db, CloudAssessment, p, str(assessment_id))
    audit(db, p, "security.cloud.assessment_read", record.id)
    return cloud_output(record)


@router.get("/ai/owner", response_model=InsightOutput)
def owner_ai(
    db: DB,
    p: FINANCE,
    currency: Annotated[str | None, Query(pattern=r"^[A-Z]{3}$")] = None,
):
    p = authority(db, p, "owner")
    if currency is None:
        currencies = db.scalars(
            select(CostRecord.currency)
            .where(CostRecord.organization_id == p.organization_id)
            .distinct()
            .order_by(CostRecord.currency)
            .limit(2)
        ).all()
        if len(currencies) > 1:
            raise HTTPException(
                409, "Multiple recorded currencies; specify the currency query parameter"
            )
        currency = currencies[0] if currencies else "INR"
    records = summarize(db, p, currency)
    result = generate(
        db,
        p,
        "owner",
        {
            f"recorded_spending_{currency.lower()}": records.total,
            "observed_months": len(records.months),
        },
    )
    return {**result, "currency": currency}


@router.get("/ai/hr", response_model=InsightOutput)
def hr_ai(db: DB, p: P):
    p = authority(db, p, "hr")
    employees, pending = db.execute(
        select(
            func.count(),
            func.coalesce(
                func.sum(case((Employee.verification_status == "pending", 1), else_=0)), 0
            ),
        ).where(Employee.organization_id == p.organization_id)
    ).one()
    audit(db, p, "ai.hr.summary", p.organization_id)
    return generate(
        db,
        p,
        "hr",
        {
            "employees": int(employees),
            "awaiting_verification": int(pending),
        },
    )


@router.get("/ai/projects/{project_id}", response_model=InsightOutput)
def project_ai(project_id: UUID, db: DB, p: P):
    p = authority(db, p, "devtrack")
    project_access(db, p, str(project_id))
    tasks, completed = db.execute(
        select(
            func.count(), func.coalesce(func.sum(case((Task.status == "done", 1), else_=0)), 0)
        ).where(Task.organization_id == p.organization_id, Task.project_id == str(project_id))
    ).one()
    return generate(
        db,
        p,
        "devtrack",
        {"tasks": int(tasks), "completed": int(completed)},
    )


@router.get("/ai/vader/{incident_id}", response_model=InsightOutput)
def vader_ai(incident_id: UUID, db: DB, p: P):
    p = authority(db, p, "vader")
    incident = scoped(db, Incident, p, str(incident_id))
    audit(db, p, "ai.vader.summary", incident.id)
    return generate(
        db,
        p,
        "vader",
        {
            "event_count": len(incident.event_ids),
            "policy_risk": incident.risk,
            "synthetic": incident.synthetic,
        },
    )


@router.get("/ai/risk-assessments/{assessment_id}", response_model=InsightOutput)
def risk_ai(assessment_id: UUID, db: DB, p: P):
    p = authority(db, p, "vader")
    assessment = scoped(db, RiskAssessment, p, str(assessment_id))
    result = assessment.result
    context = {
        "coverage_weight": result["coverage_weight"],
        "partial": result["partial"],
        "synthetic": assessment.synthetic,
        "known_dimensions": sum(
            item["score"] is not None for item in result["components"].values()
        ),
    }
    if result["overall_score"] is not None:
        context["policy_risk"] = result["overall_score"]
    audit(db, p, "ai.risk.summary", assessment.id)
    return generate(db, p, "vader", context)


@router.get("/ai/usage")
def ai_usage(db: DB, p: FINANCE, limit: Limit = 50, offset: Offset = 0) -> list[dict]:
    records = db.scalars(
        select(AIUsage)
        .where(AIUsage.organization_id == p.organization_id)
        .order_by(AIUsage.created_at, AIUsage.id)
        .limit(limit)
        .offset(offset)
    ).all()
    return [
        {
            "id": record.id,
            "provider": record.provider,
            "purpose": record.purpose,
            "request_id": record.request_id,
            "admission_period_start": record.admission_period_start,
            "input_units": record.input_units,
            "output_units": record.output_units,
            "estimated_cost": record.estimated_cost,
            "model": record.model,
            "currency": record.billing_currency,
            "pricing": record.pricing,
        }
        for record in records
    ]
