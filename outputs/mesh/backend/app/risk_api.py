"""Owner-versioned weights and immutable, authorized tenant risk history."""

import hashlib
import json
from datetime import datetime, timedelta
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import func, select

from app.api import DB, Limit, Offset, P
from app.models import RiskAssessment, RiskPolicy, identifier, now
from app.risk_engine import (
    ALGORITHM,
    DEFAULT_THRESHOLDS,
    DEFAULT_WEIGHTS,
    DIMENSIONS,
    calculate,
    collect,
)
from app.schemas import Input
from app.services import audit, emit, lock_tenant, scoped

router = APIRouter(prefix="/api/v1/vader")
Weight = Annotated[int, Field(strict=True, ge=0, le=100)]


class RiskPolicyInput(Input):
    weights: dict[str, Weight] = Field(default_factory=lambda: dict(DEFAULT_WEIGHTS))
    thresholds: dict[str, Weight] = Field(default_factory=lambda: dict(DEFAULT_THRESHOLDS))

    @model_validator(mode="after")
    def valid_policy(self):
        calculate(dict.fromkeys(DIMENSIONS), self.weights, self.thresholds)
        return self


class RiskPolicyOutput(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    version: int
    created_by: str
    created_at: datetime
    algorithm_version: str
    weights: dict[str, int]
    thresholds: dict[str, int]


class RiskAssessmentInput(Input):
    request_key: Annotated[str, Field(pattern=r"^[A-Za-z0-9._:-]{8,100}$")]
    policy_id: UUID | None = None
    window_hours: Annotated[int, Field(strict=True, ge=1, le=168)] = 24
    synthetic: Annotated[bool, Field(strict=True)] = False


class RiskComponentOutput(BaseModel):
    score: Annotated[int, Field(ge=0, le=100)] | None
    weight: int
    sources: list[str]
    evidence_ids: list[str]
    evidence_count: int
    evidence_truncated: bool


class RiskComparison(BaseModel):
    previous_assessment_id: str | None
    comparable: bool
    score_delta: float | None


class RiskResultOutput(BaseModel):
    algorithm_version: str
    policy_version: int
    window_hours: int
    overall_score: float | None
    classification: Literal["unassessed", "low", "medium", "high", "critical"]
    classification_provisional: bool
    coverage_weight: int
    partial: bool
    missing_dimension_lower_bound: float
    missing_dimension_upper_bound: float
    calibrated_probability: bool
    components: dict[str, RiskComponentOutput]
    thresholds: dict[str, int]
    comparison: RiskComparison
    explanation: str
    limitations: list[str]


class RiskAssessmentOutput(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    policy_id: str
    requested_by: str
    window_start: datetime
    window_end: datetime
    created_at: datetime
    synthetic: bool
    result: RiskResultOutput


def policy_reader(p):
    if p.role != "owner":
        p.require("security.read")


@router.post("/risk-policies", response_model=RiskPolicyOutput, status_code=201)
def policy_create(data: RiskPolicyInput, db: DB, p: P):
    p.require("organization.manage")
    lock_tenant(db, p.organization_id)
    version = (
        int(
            db.scalar(
                select(func.max(RiskPolicy.version)).where(
                    RiskPolicy.organization_id == p.organization_id
                )
            )
            or 0
        )
        + 1
    )
    policy = RiskPolicy(
        id=identifier(),
        organization_id=p.organization_id,
        version=version,
        created_by=p.user_id,
        algorithm_version=ALGORITHM,
        **data.model_dump(),
    )
    db.add(policy)
    db.flush()
    emit(db, p, "security.risk.policy.created", policy.id)
    return policy


@router.get("/risk-policies", response_model=list[RiskPolicyOutput])
def policies(db: DB, p: P, limit: Limit = 50, offset: Offset = 0):
    policy_reader(p)
    audit(db, p, "security.risk.policies.read", p.organization_id)
    return db.scalars(
        select(RiskPolicy)
        .where(RiskPolicy.organization_id == p.organization_id)
        .order_by(RiskPolicy.version.desc(), RiskPolicy.id)
        .limit(limit)
        .offset(offset)
    ).all()


@router.post("/risk-assessments", response_model=RiskAssessmentOutput, status_code=201)
def assess(data: RiskAssessmentInput, db: DB, p: P):
    p.require("security.read")
    lock_tenant(db, p.organization_id)
    digest = hashlib.sha256(
        json.dumps(
            data.model_dump(mode="json", exclude={"request_key"}),
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    previous = db.scalar(
        select(RiskAssessment).where(
            RiskAssessment.organization_id == p.organization_id,
            RiskAssessment.request_key == data.request_key,
        )
    )
    if previous is not None:
        if previous.request_digest != digest or previous.requested_by != p.user_id:
            raise HTTPException(409, "Risk request key is bound to another assessment")
        return previous
    policy = (
        scoped(db, RiskPolicy, p, str(data.policy_id))
        if data.policy_id
        else db.scalar(
            select(RiskPolicy)
            .where(RiskPolicy.organization_id == p.organization_id)
            .order_by(RiskPolicy.version.desc())
            .limit(1)
        )
    )
    if policy is None:
        raise HTTPException(409, "An owner must configure a risk policy first")
    if policy.algorithm_version != ALGORITHM:
        raise HTTPException(409, "This policy requires an unavailable risk algorithm version")
    end = now()
    start = end - timedelta(hours=data.window_hours)
    components = collect(db, p.organization_id, start, end, data.synthetic)
    calculation = calculate(
        {key: value["score"] for key, value in components.items()},
        policy.weights,
        policy.thresholds,
    )
    prior = db.scalar(
        select(RiskAssessment)
        .where(
            RiskAssessment.organization_id == p.organization_id,
            RiskAssessment.synthetic == data.synthetic,
        )
        .order_by(RiskAssessment.created_at.desc(), RiskAssessment.id)
        .limit(1)
    )
    comparable = bool(
        prior is not None
        and prior.policy_id == policy.id
        and prior.result.get("window_hours") == data.window_hours
        and prior.result.get("overall_score") is not None
        and calculation["overall_score"] is not None
        and {
            key
            for key, value in prior.result.get("components", {}).items()
            if value["score"] is not None
        }
        == {key for key, value in components.items() if value["score"] is not None}
    )
    delta = None
    if comparable and prior is not None:
        delta = round(calculation["overall_score"] - prior.result["overall_score"], 2)
    comparison = {
        "previous_assessment_id": prior.id if prior else None,
        "comparable": comparable,
        "score_delta": delta,
    }
    for key, value in components.items():
        value["weight"] = policy.weights[key]
    assessment = RiskAssessment(
        id=identifier(),
        organization_id=p.organization_id,
        policy_id=policy.id,
        requested_by=p.user_id,
        request_key=data.request_key,
        request_digest=digest,
        window_start=start,
        window_end=end,
        synthetic=data.synthetic,
        result={
            **calculation,
            "algorithm_version": ALGORITHM,
            "policy_version": policy.version,
            "window_hours": data.window_hours,
            "comparison": comparison,
            "components": components,
            "thresholds": policy.thresholds,
            "explanation": "Policy-weighted observed signals. Each telemetry event contributes to one dimension only; maximum rule weight per event, maximum normalized signal per dimension.",
            "limitations": [
                "Observed inputs only; no claim of complete connector or asset coverage.",
                "A partial score is provisional and renormalizes known-dimension weights; bounds vary missing dimensions only, not undetected threats.",
                "Telemetry signals use twice the retained anomaly weight capped at 100; posture/findings use documented severity levels.",
                "Unresolved code findings remain exposure signals regardless of age. Absence of findings is unknown, not proof of a clean repository.",
                "Synthetic runs exclude live code/cloud posture. No automatic enforcement or calibrated probability.",
            ],
        },
    )
    db.add(assessment)
    db.flush()
    emit(db, p, "security.risk.assessed", assessment.id)
    return assessment


@router.get("/risk-assessments", response_model=list[RiskAssessmentOutput])
def history(db: DB, p: P, limit: Limit = 50, offset: Offset = 0, synthetic: bool = False):
    p.require("security.read")
    audit(db, p, "security.risk.history.read", p.organization_id)
    return db.scalars(
        select(RiskAssessment)
        .where(
            RiskAssessment.organization_id == p.organization_id,
            RiskAssessment.synthetic == synthetic,
        )
        .order_by(RiskAssessment.created_at.desc(), RiskAssessment.id)
        .limit(limit)
        .offset(offset)
    ).all()


@router.get("/risk-assessments/{assessment_id}", response_model=RiskAssessmentOutput)
def assessment_get(assessment_id: UUID, db: DB, p: P):
    p.require("security.read")
    record = scoped(db, RiskAssessment, p, str(assessment_id))
    audit(db, p, "security.risk.assessment.read", record.id)
    return record


@router.get("/risk-summary")
def summary(db: DB, p: P) -> dict:
    p.require("security.summary")
    record = db.scalar(
        select(RiskAssessment)
        .where(
            RiskAssessment.organization_id == p.organization_id, RiskAssessment.synthetic.is_(False)
        )
        .order_by(RiskAssessment.created_at.desc(), RiskAssessment.id)
        .limit(1)
    )
    audit(db, p, "security.risk.summary.read", p.organization_id)
    if record is None:
        return {"available": False}
    return {
        "available": True,
        "assessment_id": record.id,
        "created_at": record.created_at,
        **{
            key: record.result[key]
            for key in (
                "overall_score",
                "classification",
                "partial",
                "coverage_weight",
                "calibrated_probability",
            )
        },
    }
