from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import or_, select

from app.api import DB, Limit, Offset, P
from app.devtrack import project_access
from app.enterprise_api import OWNER
from app.models import (
    AuditLog,
    Project,
    ProjectApprovalPolicy,
    ProjectComment,
    ProjectMember,
    ProjectReview,
    Sprint,
    Task,
    identifier,
)
from app.project_governance import effective_policy, eligible_reviewers, review, snapshot
from app.schemas import Input, ProjectOutput
from app.services import emit, lock_tenant, scoped

router = APIRouter(prefix="/api/v1")


class PolicyInput(Input):
    version: Annotated[int, Field(ge=1)]
    required_senior_reviews: Annotated[int, Field(ge=1, le=5)] = 1
    reviewers_must_be_members: bool = False


class ReviewInput(Input):
    comment: Annotated[str, Field(max_length=2000)] = ""


class ReviewOutput(BaseModel):
    model_config = {"from_attributes": True}
    id: str
    reviewer_id: str
    comment: str
    created_at: datetime
    eligible: bool


class ReviewState(BaseModel):
    project_id: str
    policy: dict
    required_reviews: int
    eligible_reviews: int
    reviews: list[ReviewOutput]


class ActivityOutput(BaseModel):
    model_config = {"from_attributes": True}
    id: str
    actor_id: str
    action: str
    target_id: str
    outcome: str
    created_at: datetime


@router.put("/devtrack/approval-policy", response_model=PolicyInput, status_code=201)
def policy_set(data: PolicyInput, db: DB, p: OWNER):
    lock_tenant(db, p.organization_id)
    if data.version <= snapshot(db, p.organization_id)["version"]:
        raise HTTPException(409, "Approval policy versions must increase")
    record = ProjectApprovalPolicy(
        id=identifier(), organization_id=p.organization_id, **data.model_dump()
    )
    db.add(record)
    emit(db, p, "project.approval_policy.created", record.id)
    return data


@router.get("/devtrack/approval-policy")
def policy_get(db: DB, p: P) -> dict:
    p.require("project.read")
    return snapshot(db, p.organization_id)


@router.get("/devtrack/review-queue", response_model=list[ProjectOutput])
def review_queue(db: DB, p: P, limit: Limit = 50, offset: Offset = 0):
    p.require("project.review")
    return db.scalars(
        select(Project)
        .where(
            Project.organization_id == p.organization_id,
            Project.status.in_(["proposed", "reviewed"]),
            Project.proposer_id != p.user_id,
            or_(
                Project.approval_policy["reviewers_must_be_members"].as_boolean().is_not(True),
                Project.id.in_(
                    select(ProjectMember.project_id).where(
                        ProjectMember.organization_id == p.organization_id,
                        ProjectMember.user_id == p.user_id,
                    )
                ),
            ),
        )
        .order_by(Project.created_at, Project.id)
        .limit(limit)
        .offset(offset)
    ).all()


@router.post("/projects/{project_id}/reviews", response_model=ProjectOutput)
def review_add(project_id: UUID, data: ReviewInput, db: DB, p: P):
    return review(db, p, str(project_id), data.comment)


@router.get("/projects/{project_id}/reviews", response_model=ReviewState)
def reviews(project_id: UUID, db: DB, p: P, limit: Limit = 50, offset: Offset = 0):
    p.require("project.read")
    record = scoped(db, Project, p, str(project_id))
    policy = effective_policy(record)
    if (
        p.role != "senior_developer"
        or record.status not in {"proposed", "reviewed"}
        or policy["reviewers_must_be_members"]
    ):
        project_access(db, p, record.id)
    eligible = eligible_reviewers(db, record)
    rows = db.scalars(
        select(ProjectReview)
        .where(
            ProjectReview.organization_id == p.organization_id,
            ProjectReview.project_id == record.id,
        )
        .order_by(ProjectReview.created_at, ProjectReview.id)
        .limit(limit)
        .offset(offset)
    ).all()
    return ReviewState(
        project_id=record.id,
        policy=policy,
        required_reviews=policy["required_senior_reviews"],
        eligible_reviews=len(eligible),
        reviews=[
            ReviewOutput(
                id=row.id,
                reviewer_id=row.reviewer_id,
                comment=row.comment,
                created_at=row.created_at,
                eligible=row.reviewer_id in eligible,
            )
            for row in rows
        ],
    )


@router.get("/projects/{project_id}/activity", response_model=list[ActivityOutput])
def activity(project_id: UUID, db: DB, p: P, limit: Limit = 50, offset: Offset = 0):
    p.require("project.read")
    project = project_access(db, p, str(project_id))
    targets = [AuditLog.target_id == project.id]
    for model in (Task, Sprint, ProjectComment, ProjectMember):
        targets.append(
            AuditLog.target_id.in_(
                select(model.id).where(
                    model.organization_id == p.organization_id, model.project_id == project.id
                )
            )
        )
    return db.scalars(
        select(AuditLog)
        .where(
            AuditLog.organization_id == p.organization_id,
            or_(*targets),
            or_(
                AuditLog.action.like("project.%"),
                AuditLog.action.like("task.%"),
                AuditLog.action.like("sprint.%"),
            ),
        )
        .order_by(AuditLog.created_at, AuditLog.id)
        .limit(limit)
        .offset(offset)
    ).all()
