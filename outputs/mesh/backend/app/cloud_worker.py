"""Tenant-scoped leased cloud assessment worker; no cloud mutation capability."""

import argparse
from datetime import timedelta

from fastapi import HTTPException
from sqlalchemy import or_, select

from app.auth import Principal
from app.cloud import configured_aws
from app.cloud_publication import Report, assessment_record
from app.core.db import SessionFactory, assert_runtime_role, tenant_context
from app.core.time import as_utc
from app.models import (
    CloudAssessmentJob,
    Membership,
    now,
)
from app.services import emit, lock_tenant


def assess(organization: str) -> dict:
    return configured_aws(organization).assess()


def run_once(organization_id: str, runner=assess) -> bool:
    with SessionFactory.begin() as db:
        assert_runtime_role(db)
        tenant_context(db, organization_id, "cloud-worker")
        org = lock_tenant(db, organization_id)
        if org is None:
            return False
        job = db.scalar(
            select(CloudAssessmentJob)
            .where(
                CloudAssessmentJob.organization_id == organization_id,
                or_(
                    (CloudAssessmentJob.status == "queued")
                    & (
                        CloudAssessmentJob.lease_until.is_(None)
                        | (CloudAssessmentJob.lease_until <= now())
                    ),
                    (CloudAssessmentJob.status == "running")
                    & (CloudAssessmentJob.lease_until < now()),
                ),
            )
            .order_by(CloudAssessmentJob.created_at)
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        if job is None:
            return False
        member = db.get(Membership, (organization_id, job.requested_by))
        if org.status != "active" or member is None or not member.active:
            job.status, job.lease_until = "cancelled", None
            return True
        actor = Principal(member.user_id, organization_id, member.role)
        try:
            actor.require("security.read")
        except HTTPException:
            job.status, job.lease_until = "cancelled", None
            return True
        if job.attempts >= 3:
            job.status, job.lease_until = "dead_letter", None
            job.error_code = "lease_recovery_exhausted"
            return True
        job.status, job.lease_until = "running", now() + timedelta(minutes=10)
        job.attempts += 1
        job_id, lease = job.id, job.lease_until
    report: Report | None
    error: str | None
    try:
        report = Report.model_validate(runner(organization_id))
        assessment_record(report, organization_id)
        if report.errors and not report.partial:
            raise ValueError("Assessment with unknown checks cannot be complete")
        error = None
    except Exception:
        report, error = None, "assessment_unavailable_or_invalid"
    with SessionFactory.begin() as db:
        assert_runtime_role(db)
        tenant_context(db, organization_id, "cloud-worker")
        org = lock_tenant(db, organization_id)
        current = db.scalar(
            select(CloudAssessmentJob)
            .where(
                CloudAssessmentJob.organization_id == organization_id,
                CloudAssessmentJob.id == job_id,
            )
            .with_for_update()
        )
        if (
            current is None
            or current.status != "running"
            or current.lease_until is None
            or as_utc(current.lease_until) != lease
        ):
            return True
        member = db.get(Membership, (organization_id, current.requested_by))
        if org is None or org.status != "active" or member is None or not member.active:
            current.status, current.lease_until = "cancelled", None
            return True
        actor = Principal(member.user_id, organization_id, member.role)
        try:
            actor.require("security.read")
        except HTTPException:
            current.status, current.lease_until = "cancelled", None
            return True
        if report is not None:
            assessment = assessment_record(report, organization_id, source_job_id=current.id)
            db.add(assessment)
            db.flush()
            current.status, current.lease_until = "completed", None
            current.assessment_id, current.error_code = assessment.id, None
            emit(db, actor, "security.cloud.assessed", assessment.id)
        else:
            current.status = "dead_letter" if current.attempts >= 3 else "queued"
            current.error_code = error
            current.lease_until = (
                now() + timedelta(seconds=2**current.attempts)
                if current.status == "queued"
                else None
            )
            emit(db, actor, "security.cloud.job_failed", current.id)
    return True


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--organization", required=True)
    parser.add_argument("--loop", action="store_true")
    args = parser.parse_args()
    from app.worker_health import run_loop

    run_loop(
        "cloud",
        args.organization,
        lambda: run_once(args.organization),
        repeat=args.loop,
        interval=5,
        idle_only=True,
    )
