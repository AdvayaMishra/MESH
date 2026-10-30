from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import case, func, select

from app.api import DB, Limit, Offset, P, Who
from app.auth import Principal, permission
from app.devtrack import project_access, repository_access
from app.enterprise_schemas import (
    FindingDecision,
    FindingHistoryOutput,
    RemediationOutput,
    RepositoryInput,
    RepositoryOutput,
    ScanInput,
    ScanOutput,
)
from app.finding_identity import (
    IdentityIndexInput,
    IdentityIndexResult,
    IdentityObservationPage,
    IdentityPage,
    identities,
    identity_observations,
    index_observations,
)
from app.finding_states import FINDING_STATES, FindingState
from app.github import GitHubApp
from app.models import AuditLog, Finding, Repository, RepositoryProject, ScanJob, identifier, now
from app.querying import ordered
from app.scan_stream import StreamLease, events
from app.schemas import FindingOutput
from app.services import audit, emit, scoped

router = APIRouter(prefix="/api/v1")


@router.post("/repositories", response_model=RepositoryOutput, status_code=201)
def repository_add(
    data: RepositoryInput,
    db: DB,
    p: Annotated[Principal, Depends(permission("organization.manage"))],
):
    project_access(db, p, str(data.project_id))
    if not GitHubApp().authorized(data.full_name, data.installation_id, p.organization_id):
        raise HTTPException(
            403, "Repository is not authorized by the configured GitHub installation"
        )
    record = Repository(
        id=identifier(),
        organization_id=p.organization_id,
        full_name=data.full_name,
        installation_id=data.installation_id,
        enabled=True,
    )
    db.add(record)
    db.flush()
    db.add(
        RepositoryProject(
            organization_id=p.organization_id,
            repository_id=record.id,
            project_id=str(data.project_id),
        )
    )
    emit(db, p, "repository.authorized", record.id)
    return record


@router.post("/repositories/{repository_id}/revoke", response_model=RepositoryOutput)
def repository_revoke(
    repository_id: UUID, db: DB, p: Annotated[Principal, Depends(permission("organization.manage"))]
):
    record = scoped(db, Repository, p, str(repository_id), lock=True)
    record.enabled = False
    emit(db, p, "repository.revoked", record.id)
    return record


@router.post("/scans", response_model=ScanOutput, status_code=202)
def scan_request(
    data: ScanInput, db: DB, p: Annotated[Principal, Depends(permission("repository.scan"))]
):
    repository = repository_access(db, p, str(data.repository_id), manage=True)
    if not repository.enabled:
        raise HTTPException(409, "Repository authorization is revoked")
    existing = db.scalar(
        select(ScanJob).where(
            ScanJob.organization_id == p.organization_id, ScanJob.request_key == data.request_key
        )
    )
    if existing:
        if existing.repository_id != repository.id or existing.commit_sha != data.commit_sha:
            raise HTTPException(409, "Idempotency key is bound to another scan")
        return existing
    job = ScanJob(
        id=identifier(),
        organization_id=p.organization_id,
        repository_id=repository.id,
        requested_by=p.user_id,
        commit_sha=data.commit_sha,
        request_key=data.request_key,
    )
    db.add(job)
    db.flush()
    emit(db, p, "repository.scan.requested", job.id)
    return job


@router.get("/scans/{job_id}", response_model=ScanOutput)
def scan_status(job_id: UUID, db: DB, p: P):
    p.require("repository.read")
    job = scoped(db, ScanJob, p, str(job_id))
    repository_access(db, p, job.repository_id)
    return job


@router.get(
    "/scans/{job_id}/events",
    response_class=StreamingResponse,
    responses={200: {"content": {"text/event-stream": {"schema": {"type": "string"}}}}},
)
def scan_events(job_id: UUID, request: Request, db: DB, p: P, who: Who):
    """Latest-state SSE snapshots; reconnect after 30 seconds, no replay guarantee."""
    p.require("repository.read")
    job = scoped(db, ScanJob, p, str(job_id))
    if not repository_access(db, p, job.repository_id).enabled:
        raise HTTPException(403, "Repository authorization was revoked")
    audit(db, p, "repository.scan.stream", job.id)
    lease = StreamLease(p)
    lease.claim()
    return StreamingResponse(
        events(who, p, job.id, request, lease),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )


@router.post("/scans/{job_id}/cancel", response_model=ScanOutput)
def scan_cancel(
    job_id: UUID, db: DB, p: Annotated[Principal, Depends(permission("repository.scan"))]
):
    """Fence queued/running work; active tools stop at a phase boundary or timeout."""
    job = scoped(db, ScanJob, p, str(job_id), lock=True)
    repository_access(db, p, job.repository_id, manage=True)
    if job.status == "cancelled":
        return job
    if job.status not in {"queued", "running"}:
        raise HTTPException(409, "Only queued or running scans can be cancelled")
    job.status, job.lease_until = "cancelled", None
    job.report = {
        **job.report,
        "stage": "cancelled",
        "updated_at": now().isoformat(),
    }
    emit(db, p, "repository.scan.cancelled", job.id)
    return job


@router.get("/repositories/{repository_id}/scans", response_model=list[ScanOutput])
def repository_scans(
    repository_id: UUID,
    db: DB,
    p: P,
    limit: Limit = 50,
    offset: Offset = 0,
    status: Literal["queued", "running", "completed", "failed", "dead_letter", "cancelled"]
    | None = None,
    requested_by: UUID | None = None,
    sort_by: Literal["created_at", "attempts", "status"] = "created_at",
    direction: Literal["asc", "desc"] = "asc",
):
    p.require("repository.read")
    repository_access(db, p, str(repository_id))
    query = select(ScanJob).where(
        ScanJob.organization_id == p.organization_id,
        ScanJob.repository_id == str(repository_id),
    )
    if status is not None:
        query = query.where(ScanJob.status == status)
    if requested_by is not None:
        query = query.where(ScanJob.requested_by == str(requested_by))
    return db.scalars(
        ordered(query, ScanJob, sort_by, direction, {"created_at", "attempts", "status"})
        .limit(limit)
        .offset(offset)
    ).all()


@router.get("/repositories/{repository_id}/remediation", response_model=RemediationOutput)
def repository_remediation(
    repository_id: UUID,
    db: DB,
    p: P,
    limit: Limit = 50,
    offset: Offset = 0,
    scanner: Literal["semgrep", "bandit", "gitleaks", "osv"] | None = None,
    severity: Literal["critical", "high", "medium", "low", "info"] | None = None,
    observed_since: datetime | None = None,
):
    """Group finding observations, not deduplicated vulnerabilities or verified fixes.

    Counts use current analyst dispositions. Observation timestamps do not imply
    resolution timestamps or independently verified remediation.
    """
    p.require("finding.read")
    repository_access(db, p, str(repository_id))
    if observed_since is not None and observed_since.utcoffset() is None:
        raise HTTPException(422, "observed_since requires an explicit timezone")
    scope = [
        Finding.organization_id == p.organization_id,
        Finding.repository_id == str(repository_id),
    ]
    if scanner is not None:
        scope.append(Finding.scanner == scanner)
    if severity is not None:
        scope.append(Finding.severity == severity)
    if observed_since is not None:
        scope.append(Finding.created_at >= observed_since)
    # Window count and groups share one SQL snapshot during concurrent writes.
    dispositions = FINDING_STATES
    query = (
        select(
            Finding.scanner,
            Finding.rule_id,
            Finding.severity,
            *(func.sum(case((Finding.status == state, 1), else_=0)) for state in dispositions),
            func.count(),
            func.min(Finding.created_at),
            func.max(Finding.created_at),
            func.count().over(),
        )
        .where(*scope)
        .group_by(Finding.scanner, Finding.rule_id, Finding.severity)
        .order_by(Finding.scanner, Finding.rule_id, Finding.severity)
    )
    # Keep the window count available even when offset is past the last group.
    rows = db.execute(query.limit(limit).offset(offset)).all()
    total_groups = int(rows[0][-1]) if rows else 0
    if not rows and offset:
        total_groups = int(db.scalar(select(func.count()).select_from(query.subquery())) or 0)
    groups = []
    for row in rows:
        groups.append(
            dict(
                scanner=row[0],
                rule_id=row[1],
                severity=row[2],
                **dict(
                    zip(
                        dispositions,
                        (int(value) for value in row[3 : 3 + len(dispositions)]),
                        strict=True,
                    )
                ),
                total=int(row[3 + len(dispositions)]),
                first_observed_at=row[4 + len(dispositions)],
                last_observed_at=row[5 + len(dispositions)],
            )
        )
    audit(db, p, "repository.remediation.read", str(repository_id))
    return {"groups": groups, "total_groups": total_groups, "limit": limit, "offset": offset}


@router.patch("/findings/{finding_id}")
def finding_decide(finding_id: UUID, data: FindingDecision, db: DB, p: P) -> dict[str, str]:
    p.require("finding.read")
    finding = scoped(db, Finding, p, str(finding_id), lock=True)
    repository_access(db, p, finding.repository_id, manage=True)
    if finding.status == data.status:
        return {"id": finding.id, "status": finding.status}
    previous = finding.status
    finding.status = data.status
    emit(db, p, "finding.status.changed", finding.id)
    audit(db, p, f"finding.transition.{previous}.{data.status}", finding.id)
    return {"id": finding.id, "status": finding.status}


@router.get("/findings/{finding_id}/history", response_model=FindingHistoryOutput)
def finding_history(finding_id: UUID, db: DB, p: P, limit: Limit = 50, offset: Offset = 0) -> dict:
    p.require("finding.read")
    finding = scoped(db, Finding, p, str(finding_id))
    repository_access(db, p, finding.repository_id)
    rows = db.scalars(
        select(AuditLog)
        .where(
            AuditLog.organization_id == p.organization_id,
            AuditLog.target_id == finding.id,
            AuditLog.action.like("finding.transition.%"),
        )
        .order_by(AuditLog.created_at, AuditLog.id)
        .limit(limit)
        .offset(offset)
    ).all()
    changes = []
    for row in rows:
        parts = row.action.split(".")
        if len(parts) == 4 and parts[2] in FINDING_STATES and parts[3] in FINDING_STATES:
            changes.append(
                {
                    "id": row.id,
                    "actor_id": row.actor_id,
                    "from_status": parts[2],
                    "to_status": parts[3],
                    "at": row.created_at,
                }
            )
    audit(db, p, "finding.history.read", finding.id)
    return {
        "changes": changes,
        "limit": limit,
        "offset": offset,
        "provenance": "Explicit transitions recorded since history support was deployed; older generic audits do not reveal before/after states.",
        "resolution": "Analyst disposition, not independently verified fix evidence.",
    }


@router.get("/repositories/{repository_id}/findings", response_model=list[FindingOutput])
def findings(
    repository_id: UUID,
    db: DB,
    p: P,
    limit: Limit = 50,
    offset: Offset = 0,
    severity: Literal["critical", "high", "medium", "low", "info"] | None = None,
    status: FindingState | None = None,
    scanner: Literal["semgrep", "bandit", "gitleaks", "osv"] | None = None,
    scan_job_id: UUID | None = None,
    commit_sha: Annotated[str | None, Query(pattern=r"^[a-f0-9]{40}$")] = None,
    dependency_name: Annotated[str | None, Query(min_length=1, max_length=200)] = None,
    sort_by: Literal["created_at", "severity", "file_path"] = "created_at",
    direction: Literal["asc", "desc"] = "asc",
):
    p.require("finding.read")
    repository_access(db, p, str(repository_id))
    query = select(Finding).where(
        Finding.organization_id == p.organization_id, Finding.repository_id == str(repository_id)
    )
    if severity is not None:
        query = query.where(Finding.severity == severity)
    if status is not None:
        query = query.where(Finding.status == status)
    if scanner is not None:
        query = query.where(Finding.scanner == scanner)
    if scan_job_id is not None:
        query = query.where(Finding.scan_job_id == str(scan_job_id))
    if commit_sha is not None:
        query = query.where(Finding.commit_sha == commit_sha)
    if dependency_name is not None:
        query = query.where(Finding.dependency["name"].as_string() == dependency_name)
    column = (
        case(
            {"critical": 5, "high": 4, "medium": 3, "low": 2, "info": 1},
            value=Finding.severity,
            else_=0,
        )
        if sort_by == "severity"
        else Finding.file_path
        if sort_by == "file_path"
        else Finding.created_at
    )
    audit(db, p, "repository.findings.read", str(repository_id))
    return db.scalars(
        query.order_by(column.desc() if direction == "desc" else column.asc(), Finding.id)
        .offset(offset)
        .limit(limit)
    ).all()


@router.get("/repositories/{repository_id}/analytics")
def repository_analytics(repository_id: UUID, db: DB, p: P) -> dict[str, dict[str, int]]:
    p.require("finding.read")
    repository_access(db, p, str(repository_id))
    scope = (
        Finding.organization_id == p.organization_id,
        Finding.repository_id == str(repository_id),
    )
    # Aggregate in PostgreSQL; finding histories may span many scan runs.
    severity: dict[str, int] = {}
    statuses: dict[str, int] = {}
    # One grouped snapshot keeps both totals consistent during concurrent scans.
    for level, status, count in db.execute(
        select(Finding.severity, Finding.status, func.count())
        .where(*scope)
        .group_by(Finding.severity, Finding.status)
    ):
        severity[level] = severity.get(level, 0) + count
        statuses[status] = statuses.get(status, 0) + count
    audit(db, p, "repository.analytics.read", str(repository_id))
    return {"severity": severity, "status": statuses}


@router.get("/repositories/{repository_id}/finding-identities", response_model=IdentityPage)
def finding_identities(
    repository_id: UUID,
    db: DB,
    p: P,
    limit: Limit = 50,
    offset: Offset = 0,
    scanner: Literal["semgrep", "bandit", "gitleaks", "osv"] | None = None,
    status: FindingState | None = None,
):
    return identities(db, p, str(repository_id), limit, offset, scanner, status)


@router.post(
    "/repositories/{repository_id}/finding-identities/index", response_model=IdentityIndexResult
)
def finding_identities_index(repository_id: UUID, data: IdentityIndexInput, db: DB, p: P):
    return index_observations(db, p, str(repository_id), data.limit)


@router.get(
    "/finding-identities/{identity_id}/observations", response_model=IdentityObservationPage
)
def finding_identity_observations(
    identity_id: UUID, db: DB, p: P, limit: Limit = 50, offset: Offset = 0
):
    return identity_observations(db, p, str(identity_id), limit, offset)
