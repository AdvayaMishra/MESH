from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.api import DB, Limit, Offset, P
from app.cloud_configuration import connection_status
from app.cloud_context import authorize
from app.models import CloudAssessmentJob, identifier, now
from app.schemas import Input
from app.services import emit, lock_tenant, scoped

router = APIRouter(prefix="/api/v1/vader/cloud/jobs")


class CloudJobInput(Input):
    request_key: Annotated[str, Field(min_length=8, max_length=100)]
    provider: Literal["aws"] = "aws"


class CloudJobOutput(BaseModel):
    model_config = {"from_attributes": True}
    id: str
    provider: str
    status: str
    attempts: int
    assessment_id: str | None
    error_code: str | None
    created_at: datetime


@router.post("", response_model=CloudJobOutput, status_code=202)
def request_assessment(data: CloudJobInput, db: DB, p: P):
    p.require("security.read")
    lock_tenant(db, p.organization_id)
    authorize(db, p)
    existing = db.scalar(
        select(CloudAssessmentJob).where(
            CloudAssessmentJob.organization_id == p.organization_id,
            CloudAssessmentJob.request_key == data.request_key,
        )
    )
    if existing:
        if existing.provider != data.provider or existing.requested_by != p.user_id:
            raise HTTPException(409, "Request key is bound to another actor or provider")
        return existing
    if connection_status(p.organization_id, "posture").state != "configured_unverified":
        raise HTTPException(
            503, "An operator-configured AWS posture role is required before collection"
        )
    job = CloudAssessmentJob(
        id=identifier(),
        organization_id=p.organization_id,
        requested_by=p.user_id,
        request_key=data.request_key,
        provider=data.provider,
    )
    db.add(job)
    emit(db, p, "security.cloud.job_requested", job.id)
    return job


@router.get("", response_model=list[CloudJobOutput])
def jobs(db: DB, p: P, limit: Limit = 50, offset: Offset = 0):
    authorize(db, p)
    return db.scalars(
        select(CloudAssessmentJob)
        .where(CloudAssessmentJob.organization_id == p.organization_id)
        .order_by(CloudAssessmentJob.created_at, CloudAssessmentJob.id)
        .limit(limit)
        .offset(offset)
    ).all()


@router.get("/{job_id}", response_model=CloudJobOutput)
def job_status(job_id: UUID, db: DB, p: P):
    authorize(db, p)
    return scoped(db, CloudAssessmentJob, p, str(job_id))


@router.post("/{job_id}/cancel", response_model=CloudJobOutput)
def cancel(job_id: UUID, db: DB, p: P):
    p.require("security.read")
    job = scoped(db, CloudAssessmentJob, p, str(job_id), lock=True)
    authorize(db, p)
    if job.status not in {"queued", "running"}:
        raise HTTPException(409, "Cloud job is no longer cancellable")
    job.status, job.lease_until = "cancelled", None
    emit(db, p, "security.cloud.job_cancelled", job.id)
    return job


@router.post("/{job_id}/retry", response_model=CloudJobOutput)
def retry(job_id: UUID, db: DB, p: P):
    p.require("security.read")
    job = scoped(db, CloudAssessmentJob, p, str(job_id), lock=True)
    authorize(db, p)
    if job.status != "dead_letter":
        raise HTTPException(409, "Only dead-letter jobs can be retried")
    if connection_status(p.organization_id, "posture").state != "configured_unverified":
        raise HTTPException(
            503, "An operator-configured AWS posture role is required before collection"
        )
    job.status, job.attempts, job.lease_until, job.error_code = "queued", 0, now(), None
    emit(db, p, "security.cloud.job_retry_approved", job.id)
    return job
