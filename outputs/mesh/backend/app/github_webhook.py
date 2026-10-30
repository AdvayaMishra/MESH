"""Signed GitHub lifecycle events; payloads never choose their own tenant."""

import hashlib
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.api import DB
from app.auth import Principal
from app.core.config import settings
from app.core.db import tenant_context
from app.enterprise_schemas import ScanInput
from app.models import Membership, Repository, ScanJob, WebhookDelivery, identifier
from app.scan_api import scan_request
from app.security import verify_webhook
from app.services import emit, lock_tenant

router = APIRouter(prefix="/api/v1/webhooks")


class Installation(BaseModel):
    id: Annotated[int, Field(gt=0, strict=True)]


class RepositoryInfo(BaseModel):
    full_name: Annotated[str, Field(pattern=r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$", max_length=200)]


class Payload(BaseModel):
    installation: Installation | None = None
    repository: RepositoryInfo | None = None
    action: Annotated[str | None, Field(max_length=50)] = None
    after: Annotated[str | None, Field(pattern=r"^[a-f0-9]{40}$")] = None
    deleted: bool = False
    repositories_removed: list[RepositoryInfo] = Field(default_factory=list, max_length=1000)


class WebhookOutput(BaseModel):
    accepted: bool = True
    duplicate: bool = False
    status: str
    scan_id: str | None = None


@router.post("/github", response_model=WebhookOutput)
async def github_webhook(
    request: Request,
    db: DB,
    signature: Annotated[str, Header(alias="X-Hub-Signature-256", max_length=100)],
    delivery: Annotated[UUID, Header(alias="X-GitHub-Delivery")],
    event: Annotated[str, Header(alias="X-GitHub-Event", pattern=r"^[a-z_]{1,50}$")],
):
    return await run_in_threadpool(
        process_github, await request.body(), db, signature, delivery, event
    )


def process_github(
    body: bytes, db: Session, signature: str, delivery: UUID, event: str
) -> WebhookOutput:
    config = settings()
    secrets = [
        secret
        for secret in (config.github_webhook_secret, config.github_webhook_previous_secret)
        if secret and len(secret.get_secret_value()) >= 32
    ]
    if not secrets:
        raise HTTPException(503, "GitHub webhook verification is not configured")
    valid = [
        verify_webhook(body, signature, secret.get_secret_value().encode()) for secret in secrets
    ]
    if not any(valid):
        raise HTTPException(401, "Invalid webhook signature")
    try:
        data = Payload.model_validate_json(body)
    except (ValidationError, ValueError, RecursionError):
        raise HTTPException(422, "Invalid GitHub event envelope") from None
    if event == "ping":
        return WebhookOutput(status="verified_ping")
    installation_id = data.installation.id if data.installation else None
    organization = (
        config.github_installations.get(str(installation_id)) if installation_id else None
    )
    if organization is None:
        return WebhookOutput(status="ignored_unbound_installation")
    tenant_context(db, organization, "github-webhook")
    org = lock_tenant(db, organization)
    if org is None:
        return WebhookOutput(status="ignored_unknown_organization")
    digest = hashlib.sha256(body).hexdigest()
    existing = db.scalar(
        select(WebhookDelivery).where(
            WebhookDelivery.organization_id == organization,
            WebhookDelivery.provider == "github",
            WebhookDelivery.delivery_id == str(delivery),
        )
    )
    if existing is None:
        existing = db.scalar(
            select(WebhookDelivery).where(
                WebhookDelivery.organization_id == organization,
                WebhookDelivery.provider == "github",
                WebhookDelivery.payload_digest == digest,
            )
        )
    if existing:
        if existing.payload_digest != digest or existing.event != event:
            raise HTTPException(409, "Delivery identifier is bound to another event")
        return WebhookOutput(duplicate=True, **existing.result)
    actor = Principal("github-webhook", organization, "system")
    result = WebhookOutput(status="ignored_event")
    if event == "installation" and data.action in {"deleted", "suspend"}:
        repositories = db.scalars(
            select(Repository).where(
                Repository.organization_id == organization,
                Repository.installation_id == installation_id,
            )
        ).all()
        for repository in repositories:
            repository.enabled = False
        jobs = db.scalars(
            select(ScanJob).where(
                ScanJob.organization_id == organization,
                ScanJob.repository_id.in_([repo.id for repo in repositories]),
                ScanJob.status.in_(["queued", "running"]),
            )
        ).all()
        for job in jobs:
            job.status, job.lease_until = "cancelled", None
        result.status = "installation_revoked"
        emit(db, actor, "github.installation.revoked", organization)
    elif event == "installation_repositories" and data.action == "removed":
        names = [repo.full_name.lower() for repo in data.repositories_removed]
        query = select(Repository).where(
            Repository.organization_id == organization,
            Repository.installation_id == installation_id,
        )
        # GitHub can omit removed names when switching all -> selected. Revoke
        # all local grants until owner reauthorization rather than retain unknown access.
        if names:
            query = query.where(func.lower(Repository.full_name).in_(names))
        repositories = db.scalars(query).all()
        for repository in repositories:
            repository.enabled = False
        jobs = db.scalars(
            select(ScanJob).where(
                ScanJob.organization_id == organization,
                ScanJob.repository_id.in_([repo.id for repo in repositories]),
                ScanJob.status.in_(["queued", "running"]),
            )
        ).all()
        for job in jobs:
            job.status, job.lease_until = "cancelled", None
        result.status = "repositories_revoked"
        emit(db, actor, "github.repositories.revoked", organization)
    elif event in {"installation", "installation_repositories"}:
        result.status = "owner_review_required"
        emit(db, actor, "github.installation.review_required", organization)
    elif event == "push" and not data.deleted and data.repository and data.after:
        push_repository = db.scalar(
            select(Repository).where(
                Repository.organization_id == organization,
                Repository.installation_id == installation_id,
                func.lower(Repository.full_name) == data.repository.full_name.lower(),
                Repository.enabled.is_(True),
            )
        )
        user = config.github_scan_actors.get(organization)
        member = db.get(Membership, (organization, user)) if user else None
        if org.status != "active" or push_repository is None:
            result.status = "ignored_unavailable_repository"
        elif member is None or not member.active:
            result.status = "ignored_missing_scan_actor"
        else:
            scanner = Principal(member.user_id, organization, member.role)
            try:
                scanner.require("repository.scan")
                job = scan_request(
                    ScanInput(
                        repository_id=UUID(push_repository.id),
                        commit_sha=data.after,
                        request_key="github-commit-" + push_repository.id + "-" + data.after,
                    ),
                    db,
                    scanner,
                )
                result.status, result.scan_id = "scan_queued", job.id
            except HTTPException as exc:
                if exc.status_code not in {403, 404, 409}:
                    raise
                result.status = "ignored_unauthorized_scan_actor"
    db.add(
        WebhookDelivery(
            id=identifier(),
            organization_id=organization,
            provider="github",
            delivery_id=str(delivery),
            event=event,
            payload_digest=digest,
            result=result.model_dump(exclude={"accepted", "duplicate"}),
        )
    )
    return result
