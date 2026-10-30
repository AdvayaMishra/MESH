"""Leased billing worker; ambiguous dispatched reads are never automatically repeated."""

import argparse
from datetime import timedelta

from fastapi import HTTPException
from sqlalchemy import or_, select

from app.auth import Principal
from app.aws_billing import AWSBillingReport, configured_billing, period_bounds
from app.billing_collections import binding, validate_report
from app.core.config import settings
from app.core.db import SessionFactory, assert_runtime_role, tenant_context
from app.core.time import as_utc
from app.models import BillingCollection, IdentitySession, Membership, identifier, now
from app.services import emit, lock_tenant


def collect(organization_id: str, period: str) -> AWSBillingReport:
    return configured_billing(organization_id).collect(period)


def authorized(db, job, organization) -> bool:
    tenant_context(db, job.organization_id, job.requested_by)
    member = db.get(Membership, (job.organization_id, job.requested_by), populate_existing=True)
    if (
        organization is None
        or organization.status != "active"
        or member is None
        or not member.active
    ):
        return False
    try:
        Principal(member.user_id, job.organization_id, member.role).require("finance.write")
    except HTTPException:
        return False
    if member.access_not_before is not None and as_utc(job.created_at) <= as_utc(
        member.access_not_before
    ):
        return False
    if settings().require_privileged_mfa and job.requested_aal != "aal2":
        return False
    if job.requested_session_id is None:
        return settings().test_mode
    identity = db.scalar(
        select(IdentitySession)
        .where(
            IdentitySession.user_id == job.requested_by,
            IdentitySession.provider_session_id == job.requested_session_id,
        )
        .execution_options(populate_existing=True)
    )
    return (
        identity is not None and identity.revoked_at is None and as_utc(identity.expires_at) > now()
    )


def matches_binding(job) -> bool:
    try:
        identity, revision = binding(job.organization_id)
    except HTTPException:
        return False
    return identity.account_id == job.provider_account_id and revision == job.binding_revision


def finish(db, job, status, error):
    job.status, job.lease_until, job.finished_at, job.error_code = status, None, now(), error
    emit(
        db,
        Principal(job.requested_by, job.organization_id, "owner"),
        "finance.billing." + status,
        job.id,
    )


def run_once(organization_id: str, runner=collect) -> bool:
    with SessionFactory.begin() as db:
        assert_runtime_role(db)
        tenant_context(db, organization_id, "billing-worker")
        organization = lock_tenant(db, organization_id)
        if organization is None:
            return False
        job = db.scalar(
            select(BillingCollection)
            .where(
                BillingCollection.organization_id == organization_id,
                BillingCollection.synthetic.is_(False),
                or_(
                    BillingCollection.status == "queued",
                    (BillingCollection.status == "running")
                    & (BillingCollection.lease_until < now()),
                ),
            )
            .order_by(BillingCollection.created_at, BillingCollection.id)
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        if job is None:
            return False
        if job.status == "running":
            finish(db, job, "ambiguous", "dispatch_outcome_unknown")
            return True
        if not authorized(db, job, organization):
            finish(db, job, "cancelled", "authority_revoked")
            return True
        if not matches_binding(job):
            finish(db, job, "cancelled", "billing_binding_changed")
            return True
        try:
            period_bounds(job.period, now().date())
        except ValueError:
            finish(db, job, "cancelled", "period_out_of_window")
            return True
        job.status, job.attempts = "running", 1
        job.dispatch_token, job.dispatched_at = identifier(), now()
        job.lease_until = now() + timedelta(minutes=5)
        job_id, token, period = job.id, job.dispatch_token, job.period
        emit(
            db,
            Principal(job.requested_by, organization_id, "owner"),
            "finance.billing.dispatched",
            job.id,
        )
    # The dispatch marker has committed; no organization lock is held during AWS calls.
    report = None
    error = None
    try:
        output = runner(organization_id, period)
        report = AWSBillingReport.model_validate(
            output.model_dump() if isinstance(output, AWSBillingReport) else output
        )
    except Exception:
        error = "provider_unavailable_or_invalid"
    with SessionFactory.begin() as db:
        assert_runtime_role(db)
        tenant_context(db, organization_id, "billing-worker")
        organization = lock_tenant(db, organization_id)
        current = db.scalar(
            select(BillingCollection)
            .where(
                BillingCollection.organization_id == organization_id, BillingCollection.id == job_id
            )
            .with_for_update()
        )
        if current is None or current.status != "running" or current.dispatch_token != token:
            return True
        if current.lease_until is None or as_utc(current.lease_until) <= now():
            finish(db, current, "ambiguous", "dispatch_outcome_unknown")
        elif not authorized(db, current, organization):
            finish(db, current, "cancelled", "authority_revoked")
        elif not matches_binding(current):
            finish(db, current, "cancelled", "billing_binding_changed")
        else:
            if report is not None:
                try:
                    validate_report(current, report)
                except ValueError:
                    report, error = None, "provider_scope_or_time_mismatch"
            if report is None:
                finish(db, current, "failed", error)
            else:
                current.report = report.model_dump(mode="json")
                finish(db, current, "completed", None)
    return True


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--organization", required=True)
    parser.add_argument("--loop", action="store_true")
    args = parser.parse_args()
    from app.worker_health import run_loop

    run_loop(
        "billing",
        args.organization,
        lambda: run_once(args.organization),
        repeat=args.loop,
        interval=5,
        idle_only=True,
    )
