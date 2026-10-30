from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import Principal
from app.core.time import as_utc
from app.models import Membership, Project, ProjectMember, Repository, RepositoryProject
from app.services import scoped


def project_access(db: Session, p: Principal, project_id: str, manager: bool = False) -> Project:
    project = scoped(db, Project, p, project_id)
    if p.role == "owner":
        return project
    link = db.scalar(
        select(ProjectMember).where(
            ProjectMember.organization_id == p.organization_id,
            ProjectMember.project_id == project_id,
            ProjectMember.user_id == p.user_id,
        )
    )
    member = db.get(Membership, (p.organization_id, p.user_id))
    retained_proposer = project.proposer_id == p.user_id and (
        member is None
        or member.access_not_before is None
        or as_utc(project.created_at) > as_utc(member.access_not_before)
    )
    proposer_manager = retained_proposer and p.role == "senior_developer"
    if manager and not proposer_manager and (link is None or not link.manager):
        raise HTTPException(403, "Project manager assignment required")
    if not manager and not retained_proposer and link is None:
        raise HTTPException(404, "Record not found")
    return project


def active_developer(db: Session, p: Principal, user_id: str) -> Membership:
    member = db.get(Membership, (p.organization_id, user_id))
    if (
        member is None
        or not member.active
        or member.role not in {"senior_developer", "junior_developer"}
    ):
        raise HTTPException(422, "Active developer membership required")
    return member


def repository_access(
    db: Session, p: Principal, repository_id: str, manage: bool = False
) -> Repository:
    repository = scoped(db, Repository, p, repository_id)
    if p.role in {"owner", "security_analyst"}:
        return repository
    links = db.scalars(
        select(RepositoryProject).where(
            RepositoryProject.organization_id == p.organization_id,
            RepositoryProject.repository_id == repository_id,
        )
    ).all()
    for link in links:
        try:
            project_access(db, p, link.project_id, manager=manage)
            return repository
        except HTTPException as exc:
            if exc.status_code not in {403, 404}:
                raise
    raise HTTPException(404, "Repository not found")
