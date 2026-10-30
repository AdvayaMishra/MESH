from fastapi import HTTPException
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.auth import Principal
from app.models import (
    AuditLog,
    Membership,
    Project,
    ProjectApprovalPolicy,
    ProjectMember,
    ProjectReview,
    identifier,
)
from app.services import emit, scoped

DEFAULT = {"version": 0, "required_senior_reviews": 1, "reviewers_must_be_members": False}


def snapshot(db: Session, organization: str) -> dict:
    policy = db.scalar(
        select(ProjectApprovalPolicy)
        .where(ProjectApprovalPolicy.organization_id == organization)
        .order_by(ProjectApprovalPolicy.version.desc())
        .limit(1)
    )
    if policy is None:
        return dict(DEFAULT)
    return {
        "policy_id": policy.id,
        "version": policy.version,
        "required_senior_reviews": policy.required_senior_reviews,
        "reviewers_must_be_members": policy.reviewers_must_be_members,
    }


def effective_policy(project: Project) -> dict:
    return project.approval_policy or dict(DEFAULT)


def eligible_reviewers(db: Session, project: Project) -> set[str]:
    ids = set(
        db.scalars(
            select(ProjectReview.reviewer_id)
            .join(
                Membership,
                (Membership.organization_id == ProjectReview.organization_id)
                & (Membership.user_id == ProjectReview.reviewer_id),
            )
            .where(
                ProjectReview.organization_id == project.organization_id,
                ProjectReview.project_id == project.id,
                or_(
                    Membership.access_not_before.is_(None),
                    ProjectReview.created_at > Membership.access_not_before,
                ),
            )
        ).all()
    )
    if project.approval_policy is None:
        # Preserve genuine pre-policy review history, without inventing review records.
        ids.update(
            db.scalars(
                select(AuditLog.actor_id)
                .join(
                    Membership,
                    (Membership.organization_id == AuditLog.organization_id)
                    & (Membership.user_id == AuditLog.actor_id),
                )
                .where(
                    AuditLog.organization_id == project.organization_id,
                    AuditLog.target_id == project.id,
                    AuditLog.action == "project.reviewed",
                    or_(
                        Membership.access_not_before.is_(None),
                        AuditLog.created_at > Membership.access_not_before,
                    ),
                )
            ).all()
        )
    ids.discard(project.proposer_id)
    active = set(
        db.scalars(
            select(Membership.user_id).where(
                Membership.organization_id == project.organization_id,
                Membership.user_id.in_(ids),
                Membership.active.is_(True),
                Membership.role == "senior_developer",
            )
        ).all()
    )
    if effective_policy(project)["reviewers_must_be_members"]:
        active &= set(
            db.scalars(
                select(ProjectMember.user_id).where(
                    ProjectMember.organization_id == project.organization_id,
                    ProjectMember.project_id == project.id,
                )
            ).all()
        )
    return active


def review(db: Session, p: Principal, project_id: str, comment: str = "") -> Project:
    p.require("project.review")
    record = scoped(db, Project, p, project_id, lock=True)
    if record.proposer_id == p.user_id:
        raise HTTPException(403, "Self-review is forbidden")
    policy = effective_policy(record)
    if record.status not in {"proposed", "reviewed"}:
        raise HTTPException(409, "Project is not accepting senior reviews")
    if (
        record.status == "reviewed"
        and len(eligible_reviewers(db, record)) >= policy["required_senior_reviews"]
    ):
        raise HTTPException(409, "Project already has the required reviews")
    if policy["reviewers_must_be_members"] and not db.scalar(
        select(ProjectMember.id).where(
            ProjectMember.organization_id == p.organization_id,
            ProjectMember.project_id == project_id,
            ProjectMember.user_id == p.user_id,
        )
    ):
        raise HTTPException(403, "The proposal policy requires an assigned project reviewer")
    if db.scalar(
        select(ProjectReview.id).where(
            ProjectReview.organization_id == p.organization_id,
            ProjectReview.project_id == project_id,
            ProjectReview.reviewer_id == p.user_id,
        )
    ):
        raise HTTPException(409, "Reviewer already recorded a decision")
    db.add(
        ProjectReview(
            id=identifier(),
            organization_id=p.organization_id,
            project_id=project_id,
            reviewer_id=p.user_id,
            comment=comment,
        )
    )
    db.flush()
    emit(db, p, "project.review.recorded", project_id)
    if len(eligible_reviewers(db, record)) >= policy["required_senior_reviews"]:
        record.status = "reviewed"
        emit(db, p, "project.reviewed", project_id)
    return record
