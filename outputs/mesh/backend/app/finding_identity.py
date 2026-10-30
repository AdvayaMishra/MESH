"""Exact-metadata finding identities; no semantic equivalence or verified-fix claims."""

import hashlib
import json
from datetime import datetime
from typing import Annotated, Literal

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.auth import Principal
from app.core.time import as_utc
from app.devtrack import repository_access
from app.finding_states import FINDING_STATES, FindingState
from app.models import Finding, FindingIdentity, Membership
from app.schemas import FindingDependency, FindingOutput, Input
from app.services import audit, emit, lock_tenant

ALGORITHM = "exact-observation-v1"
MAX_FINDINGS = 10000


class FindingMatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scanner: Annotated[str, Field(min_length=1, max_length=30)]
    rule_id: Annotated[str, Field(min_length=1, max_length=200)]
    file_path: Annotated[str, Field(min_length=1, max_length=500)]
    line: Annotated[int, Field(ge=1, le=2147483647)]
    column: Annotated[int | None, Field(ge=1, le=2147483647)] = None
    dependency: FindingDependency | None = None


class NormalizedFinding(FindingMatch):
    severity: Literal["critical", "high", "medium", "low", "info"]


class IdentityIndexInput(Input):
    limit: Annotated[int, Field(ge=1, le=500)] = 200


class IdentityItem(BaseModel):
    id: str
    fingerprint: str
    algorithm_version: str
    match: FindingMatch
    observations: int
    distinct_scans: int
    observations_without_scan_provenance: int
    first_observed_at: datetime
    last_observed_at: datetime
    latest_status: str
    latest_severity: str
    latest_commit_sha: str | None
    statuses: dict[str, int]


class IdentityIndexResult(BaseModel):
    linked_observations: int
    remaining_unindexed: int
    matching_policy: str
    historical_scan_provenance_invented: Literal[False]


class IdentityObservationPage(BaseModel):
    identity_id: str
    observations: list[FindingOutput]
    total_observations: int
    limit: int
    offset: int


class IdentityPage(BaseModel):
    groups: list[IdentityItem]
    total_groups: int
    unindexed_observations: int
    limit: int
    offset: int
    matching_policy: str = ALGORITHM
    limitation: str = "Exact recorded metadata only; not semantic vulnerability deduplication or verified remediation"


def metadata(finding: Finding) -> dict:
    return FindingMatch.model_validate(
        {key: getattr(finding, key) for key in FindingMatch.model_fields}
    ).model_dump(mode="json")


def fingerprint(organization: str, repository: str, fields: dict) -> str:
    value = {
        "algorithm": ALGORITHM,
        "organization": organization,
        "repository": repository,
        "match": fields,
    }
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def link_observations(db: Session, organization: str, repository: str, rows: list[Finding]) -> None:
    if len(rows) > MAX_FINDINGS:
        raise ValueError("Finding identity batch exceeds limit")
    values = {}
    keyed = []
    for row in rows:
        if row.organization_id != organization or row.repository_id != repository:
            raise ValueError("Finding identity scope mismatch")
        fields = metadata(row)
        key = fingerprint(organization, repository, fields)
        values[key] = fields
        keyed.append((row, key))
    found = {}
    keys = list(values)
    for start in range(0, len(keys), 500):
        for identity in db.scalars(
            select(FindingIdentity).where(
                FindingIdentity.organization_id == organization,
                FindingIdentity.repository_id == repository,
                FindingIdentity.fingerprint.in_(keys[start : start + 500]),
            )
        ):
            if (
                identity.algorithm_version != ALGORITHM
                or identity.match_metadata != values[identity.fingerprint]
            ):
                raise ValueError("Stored finding identity does not match its metadata")
            found[identity.fingerprint] = identity
    for key, fields in values.items():
        if key not in found:
            identity = FindingIdentity(
                organization_id=organization,
                repository_id=repository,
                fingerprint=key,
                algorithm_version=ALGORITHM,
                match_metadata=fields,
            )
            db.add(identity)
            found[key] = identity
    db.flush()
    for row, key in keyed:
        row.identity_id = found[key].id


def index_observations(db: Session, p: Principal, repository: str, limit: int) -> dict:
    p.require("repository.scan")
    if not 1 <= limit <= 500:
        raise HTTPException(422, "Index batch must be between 1 and 500")
    org = lock_tenant(db, p.organization_id)
    if org is not None:
        db.refresh(org, attribute_names=["status"])
    actor = db.get(
        Membership, (p.organization_id, p.user_id), with_for_update=True, populate_existing=True
    )
    if org is None or org.status != "active" or actor is None or not actor.active:
        raise HTTPException(403, "Active indexing authority required")
    fresh = Principal(actor.user_id, p.organization_id, actor.role)
    fresh.require("repository.scan")
    repository_access(db, fresh, repository, manage=True)
    rows = list(
        db.scalars(
            select(Finding)
            .where(
                Finding.organization_id == p.organization_id,
                Finding.repository_id == repository,
                Finding.identity_id.is_(None),
            )
            .order_by(Finding.created_at, Finding.id)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
    )
    try:
        link_observations(db, p.organization_id, repository, rows)
    except ValueError:
        raise HTTPException(
            409, "Stored finding metadata requires review before indexing"
        ) from None
    db.flush()
    remaining = (
        db.scalar(
            select(func.count())
            .select_from(Finding)
            .where(
                Finding.organization_id == p.organization_id,
                Finding.repository_id == repository,
                Finding.identity_id.is_(None),
            )
        )
        or 0
    )
    emit(db, p, "repository.finding_identities.indexed", repository)
    return {
        "linked_observations": len(rows),
        "remaining_unindexed": int(remaining),
        "matching_policy": ALGORITHM,
        "historical_scan_provenance_invented": False,
    }


def identities(
    db: Session,
    p: Principal,
    repository: str,
    limit: int,
    offset: int,
    scanner: str | None = None,
    status: FindingState | None = None,
) -> dict:
    p.require("finding.read")
    repository_access(db, p, repository)
    audit(db, p, "repository.finding_identities.read", repository)
    scope = [
        Finding.organization_id == p.organization_id,
        Finding.repository_id == repository,
        Finding.identity_id.is_not(None),
    ]
    aggregate = (
        select(
            Finding.identity_id,
            func.count().label("observations"),
            func.count(func.distinct(Finding.scan_job_id)).label("scans"),
            func.sum(case((Finding.scan_job_id.is_(None), 1), else_=0)).label("unprovenanced"),
            func.min(Finding.created_at).label("first_seen"),
            func.max(Finding.created_at).label("last_seen"),
            *(
                func.sum(case((Finding.status == state, 1), else_=0)).label("state_" + state)
                for state in FINDING_STATES
            ),
        )
        .where(*scope)
        .group_by(Finding.identity_id)
        .subquery()
    )
    latest = (
        select(
            Finding.identity_id,
            Finding.status.label("latest_status"),
            Finding.severity.label("latest_severity"),
            Finding.commit_sha.label("latest_commit"),
            func.row_number()
            .over(
                partition_by=Finding.identity_id,
                order_by=(Finding.created_at.desc(), Finding.id.desc()),
            )
            .label("position"),
        )
        .where(*scope)
        .subquery()
    )
    query = (
        select(
            FindingIdentity,
            aggregate,
            latest.c.latest_status,
            latest.c.latest_severity,
            latest.c.latest_commit,
            func.count().over().label("total_groups"),
        )
        .join(aggregate, aggregate.c.identity_id == FindingIdentity.id)
        .join(latest, (latest.c.identity_id == FindingIdentity.id) & (latest.c.position == 1))
        .where(
            FindingIdentity.organization_id == p.organization_id,
            FindingIdentity.repository_id == repository,
        )
    )
    unindexed = (
        select(func.count())
        .select_from(Finding)
        .where(
            Finding.organization_id == p.organization_id,
            Finding.repository_id == repository,
            Finding.identity_id.is_(None),
        )
    )
    if scanner is not None:
        query = query.where(FindingIdentity.match_metadata["scanner"].as_string() == scanner)
        unindexed = unindexed.where(Finding.scanner == scanner)
    if status is not None:
        query = query.where(latest.c.latest_status == status)
        unindexed = unindexed.where(Finding.status == status)
    query = query.order_by(aggregate.c.last_seen.desc(), FindingIdentity.id)
    rows = db.execute(query.limit(limit).offset(offset)).all()
    total = (
        int(rows[0]._mapping["total_groups"])
        if rows
        else int(db.scalar(select(func.count()).select_from(query.subquery())) or 0)
    )
    groups = []
    for row in rows:
        identity, m = row[0], row._mapping
        counts = {state: int(m["state_" + state]) for state in FINDING_STATES}
        if int(m["observations"]) > sum(counts.values()):
            counts["other"] = int(m["observations"]) - sum(counts.values())
        groups.append(
            {
                "id": identity.id,
                "fingerprint": identity.fingerprint,
                "algorithm_version": identity.algorithm_version,
                "match": identity.match_metadata,
                "observations": int(m["observations"]),
                "distinct_scans": int(m["scans"]),
                "observations_without_scan_provenance": int(m["unprovenanced"]),
                "first_observed_at": as_utc(m["first_seen"]),
                "last_observed_at": as_utc(m["last_seen"]),
                "latest_status": m["latest_status"],
                "latest_severity": m["latest_severity"],
                "latest_commit_sha": m["latest_commit"],
                "statuses": counts,
            }
        )
    return {
        "groups": groups,
        "total_groups": total,
        "unindexed_observations": int(db.scalar(unindexed) or 0),
        "limit": limit,
        "offset": offset,
    }


def identity_observations(
    db: Session, p: Principal, identity_id: str, limit: int, offset: int
) -> dict:
    from app.services import scoped

    p.require("finding.read")
    identity = scoped(db, FindingIdentity, p, identity_id)
    repository_access(db, p, identity.repository_id)
    audit(db, p, "finding_identity.observations.read", identity.id)
    query = select(Finding).where(
        Finding.organization_id == p.organization_id,
        Finding.repository_id == identity.repository_id,
        Finding.identity_id == identity.id,
    )
    total = int(db.scalar(select(func.count()).select_from(query.subquery())) or 0)
    rows = db.scalars(
        query.order_by(Finding.created_at, Finding.id).limit(limit).offset(offset)
    ).all()
    return {
        "identity_id": identity.id,
        "observations": rows,
        "total_observations": total,
        "limit": limit,
        "offset": offset,
    }
