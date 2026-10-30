import hashlib
import secrets
from datetime import date, timedelta
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth import Identity, Principal, authenticated_identity, permission, principal
from app.core.db import session, tenant_context
from app.core.time import as_utc
from app.correlation import authority as security_authority
from app.devtrack import project_access, repository_access
from app.domains import create_challenge, verify_challenge
from app.identity_provider import (
    Login,
    Recover,
    Refresh,
    ResendSignup,
    Signup,
    SupabaseAuth,
    Tokens,
    Verify,
    provider_tokens,
)
from app.mail import queue_invitation
from app.models import (
    Anomaly,
    AuditLog,
    Delivery,
    Employee,
    EmploymentTerms,
    Finding,
    Incident,
    Invitation,
    Membership,
    Organization,
    Outbox,
    Payroll,
    Project,
    ProjectMember,
    ResponseAction,
    SecurityEvent,
    Task,
    TrustEvent,
    identifier,
    now,
)
from app.project_governance import effective_policy, eligible_reviewers, review, snapshot
from app.querying import ordered
from app.schemas import (
    AnomalyOutput,
    DomainInput,
    EmployeeInput,
    EmployeeOutput,
    EventInput,
    EventOutput,
    FindingOutput,
    IncidentOutput,
    InviteAccept,
    InviteDeliveryOutput,
    InviteInput,
    InviteOutput,
    OrganizationInput,
    OrganizationOutput,
    PayrollInput,
    PayrollOutput,
    ProjectDecision,
    ProjectInput,
    ProjectOutput,
    ResponseInput,
    ResponseOutput,
    SecurityEventOutput,
    SummaryOutput,
    TaskInput,
    TaskOutput,
    TrustInput,
)
from app.services import (
    accept_invitation,
    audit,
    emit,
    invitation,
    invitation_authority,
    payroll_net,
    scoped,
)
from app.sessions import revoke_all
from app.telemetry_schema import EventCategory, EventSeverity, SourceKind
from app.vader import ingest, simulate

router = APIRouter(prefix="/api/v1")
DB = Annotated[Session, Depends(session, scope="function")]
Who = Annotated[Identity, Depends(authenticated_identity)]
P = Annotated[Principal, Depends(principal)]
Limit = Annotated[int, Query(ge=1, le=100)]
Offset = Annotated[int, Query(ge=0, le=100000)]


@router.post("/auth/register", status_code=202)
def register(data: Signup):
    SupabaseAuth().signup(data)
    return {"message": "Check your email for verification instructions"}


@router.post("/auth/verify", response_model=Tokens)
def verify_email(data: Verify):
    result = SupabaseAuth().request(
        "verify", {"email": data.email, "token": data.token.get_secret_value(), "type": data.type}
    )
    return provider_tokens(result)


@router.post("/auth/login", response_model=Tokens)
def login(data: Login):
    return SupabaseAuth().login(data)


@router.post("/auth/refresh", response_model=Tokens)
def refresh(data: Refresh):
    return SupabaseAuth().refresh(data)


@router.post("/auth/recover", status_code=202)
def recover(data: Recover):
    SupabaseAuth().request(
        "recover",
        {
            "email": data.email,
            "gotrue_meta_security": {"captcha_token": data.captcha_token.get_secret_value()},
        },
    )
    return {"message": "If the account exists, recovery instructions will be sent"}


@router.post("/auth/resend", status_code=202)
def resend_signup(data: ResendSignup):
    SupabaseAuth().resend_signup(data)
    return {"message": "If signup confirmation is pending, instructions will be sent"}


@router.post("/auth/logout")
def logout(who: Who, db: DB, authorization: Annotated[str, Header()]) -> dict[str, int | str]:
    count = revoke_all(db, who.user_id, reason="logout")
    try:
        SupabaseAuth().request("logout?scope=global", {}, token=authorization.split(" ", 1)[1])
    except HTTPException:
        return {"mesh_sessions_revoked": count, "provider_logout": "unavailable"}
    return {"mesh_sessions_revoked": count, "provider_logout": "confirmed"}


@router.post("/organizations", response_model=OrganizationOutput, status_code=201)
def create_organization(data: OrganizationInput, who: Who, db: DB):
    org = Organization(id=identifier(), name=data.name)
    tenant_context(db, org.id, who.user_id)
    db.add(org)
    db.flush()
    db.add(Membership(organization_id=org.id, user_id=who.user_id, email=who.email, role="owner"))
    emit(db, Principal(who.user_id, org.id, "owner"), "organization.created", org.id)
    return org


@router.get("/organizations/current", response_model=OrganizationOutput)
def current_organization(p: P, db: DB):
    return db.get(Organization, p.organization_id)


@router.post("/organizations/domain-challenges", status_code=201)
def domain_start(
    data: DomainInput,
    db: DB,
    p: Annotated[Principal, Depends(permission("organization.manage"))],
):
    record, token = create_challenge(db, p, data.website)
    return {
        "id": record.id,
        "domain": record.domain,
        "token": token,
        "expires_at": record.expires_at,
        "website_path": "/.well-known/mesh-verification.txt",
        "dns_name": "_mesh-verification." + record.domain,
    }


@router.post("/organizations/domain-challenges/{challenge_id}/verify")
def domain_verify(
    challenge_id: UUID, db: DB, p: Annotated[Principal, Depends(permission("organization.manage"))]
):
    return verify_challenge(db, p, str(challenge_id))


@router.post("/invitations", response_model=InviteOutput, status_code=201)
def create_invitation(data: InviteInput, p: P, db: DB):
    record, token = invitation(db, p, data.email, data.role)
    queue_invitation(db, record, token)
    return InviteOutput(
        id=record.id,
        email=record.email,
        role=record.role,
        status=record.status,
        expires_at=record.expires_at,
    )


def invitation_reader(p: Principal) -> None:
    if p.role == "owner":
        p.require("organization.manage")
    else:
        p.require("invite.employee")


@router.get("/invitations", response_model=list[InviteOutput])
def list_invitations(
    p: P,
    db: DB,
    limit: Limit = 50,
    offset: Offset = 0,
    status: Literal["pending", "accepted", "revoked"] | None = None,
):
    invitation_reader(p)
    query = select(Invitation).where(Invitation.organization_id == p.organization_id)
    if p.role != "owner":
        query = query.where(
            Invitation.role.in_(["junior_developer", "senior_developer", "security_analyst"])
        )
    if status is not None:
        query = query.where(Invitation.status == status)
    records = db.scalars(
        query.order_by(Invitation.created_at.desc(), Invitation.id).offset(offset).limit(limit)
    ).all()
    audit(db, p, "invitation.list_read", p.organization_id)
    return [
        InviteOutput(id=r.id, email=r.email, role=r.role, status=r.status, expires_at=r.expires_at)
        for r in records
    ]


@router.get("/invitations/{invitation_id}/delivery", response_model=InviteDeliveryOutput)
def invitation_delivery(invitation_id: UUID, p: P, db: DB):
    invitation_reader(p)
    record = scoped(db, Invitation, p, str(invitation_id))
    if p.role != "owner":
        p.require("invite.hr" if record.role == "hr" else "invite.employee")
    job = db.scalar(
        select(Outbox)
        .where(
            Outbox.organization_id == p.organization_id,
            Outbox.topic == "mail.invitation",
            Outbox.payload["invitation_id"].as_string() == record.id,
        )
        .order_by(Outbox.created_at.desc(), Outbox.id.desc())
        .limit(1)
    )
    audit(db, p, "invitation.delivery_read", record.id)
    if job is None:
        return InviteDeliveryOutput(invitation_id=record.id, state="not_queued")
    raw_outcome = job.payload.get("outcome")
    outcome = (
        raw_outcome
        if raw_outcome
        in {"smtp_accepted", "skipped_inactive", "skipped_expired", "skipped_superseded"}
        else None
    )
    state: Literal[
        "not_queued",
        "queued",
        "retrying",
        "failed",
        "smtp_accepted",
        "skipped",
        "processed_unknown",
    ] = "failed" if job.status == "dead_letter" else "retrying" if job.attempts else "queued"
    processed_at = None
    if job.status == "delivered":
        state = (
            "smtp_accepted"
            if outcome == "smtp_accepted"
            else "skipped"
            if outcome
            else "processed_unknown"
        )
        processed_at = db.scalar(
            select(Delivery.created_at)
            .where(
                Delivery.organization_id == p.organization_id,
                Delivery.message_id == job.id,
                Delivery.consumer == "local-event-receipt",
            )
            .order_by(Delivery.created_at.desc())
            .limit(1)
        )
    return InviteDeliveryOutput(
        invitation_id=record.id,
        job_id=job.id,
        state=state,
        attempts=job.attempts,
        queued_at=job.created_at,
        next_attempt_at=job.available_at if job.status == "pending" else None,
        processed_at=processed_at,
        outcome=outcome,
    )


@router.post("/invitations/accept")
def accept(
    data: InviteAccept,
    who: Who,
    db: DB,
    organization: Annotated[UUID, Header(alias="X-Organization-ID")],
):
    org = str(organization)
    tenant_context(db, org, who.user_id)
    organization_row = db.get(Organization, org)
    if not organization_row or organization_row.status != "active":
        raise HTTPException(403, "Organization unavailable")
    member = accept_invitation(db, Principal(who.user_id, org, ""), who, data.token)
    return {"organization_id": org, "role": member.role}


@router.delete("/invitations/{invitation_id}", status_code=204)
def cancel_invitation(invitation_id: UUID, p: P, db: DB):
    preview = scoped(db, Invitation, p, str(invitation_id))
    p = invitation_authority(db, p, preview.role)
    record = scoped(db, Invitation, p, str(invitation_id), lock=True)
    p.require("invite.hr" if record.role == "hr" else "invite.employee")
    if record.status != "pending":
        raise HTTPException(409, "Invitation is no longer pending")
    record.status = "revoked"
    emit(db, p, "invitation.revoked", record.id)


@router.post("/invitations/{invitation_id}/resend", response_model=InviteOutput, status_code=202)
def resend_invitation(invitation_id: UUID, p: P, db: DB):
    preview = scoped(db, Invitation, p, str(invitation_id))
    p = invitation_authority(db, p, preview.role)
    record = scoped(db, Invitation, p, str(invitation_id), lock=True)
    p.require("invite.hr" if record.role == "hr" else "invite.employee")
    if record.status != "pending":
        raise HTTPException(409, "Only pending invitations may be resent")
    last = db.scalar(
        select(Outbox.created_at)
        .where(
            Outbox.organization_id == p.organization_id,
            Outbox.topic == "mail.invitation",
            Outbox.payload["invitation_id"].as_string() == record.id,
        )
        .order_by(Outbox.created_at.desc())
        .limit(1)
    )
    if last is not None and as_utc(last) > now() - timedelta(seconds=60):
        raise HTTPException(429, "Wait before resending invitation", headers={"Retry-After": "60"})
    token = secrets.token_urlsafe(48)
    record.token_hash = hashlib.sha256(token.encode()).hexdigest()
    record.creator_id = p.user_id
    record.expires_at = now() + timedelta(days=3)
    queue_invitation(db, record, token)
    emit(db, p, "invitation.resent", record.id)
    return InviteOutput(
        id=record.id,
        email=record.email,
        role=record.role,
        status=record.status,
        expires_at=record.expires_at,
    )


@router.post("/employees", response_model=EmployeeOutput, status_code=201)
def create_employee(
    data: EmployeeInput, db: DB, p: Annotated[Principal, Depends(permission("employee.write"))]
):
    member = db.get(Membership, (p.organization_id, str(data.user_id)))
    if not member or not member.active or member.role in {"owner", "hr"}:
        raise HTTPException(422, "An active employee membership is required")
    record = Employee(
        id=identifier(),
        organization_id=p.organization_id,
        user_id=str(data.user_id),
        name=data.name,
        department=data.department,
    )
    db.add(record)
    db.flush()
    emit(db, p, "employee.created", record.id)
    return record


def employee_view(db: Session, record: Employee) -> dict:
    member = db.get(Membership, (record.organization_id, record.user_id))
    return {
        "id": record.id,
        "user_id": record.user_id,
        "name": record.name,
        "department": record.department,
        "status": record.status,
        "verification_status": record.verification_status,
        "created_at": record.created_at,
        "email": member.email if member else None,
        "app_role": member.role if member else None,
    }


@router.get("/employees", response_model=list[EmployeeOutput])
def employees(
    db: DB,
    p: Annotated[Principal, Depends(permission("employee.read"))],
    limit: Limit = 50,
    offset: Offset = 0,
    department: Annotated[str | None, Query(min_length=1, max_length=100)] = None,
    status: Literal["onboarding", "active", "offboarded"] | None = None,
    search: Annotated[str | None, Query(min_length=1, max_length=100)] = None,
    sort_by: Literal["id", "name", "created_at"] = "id",
    direction: Literal["asc", "desc"] = "asc",
):
    audit(db, p, "employee.directory.read", p.organization_id)
    query = select(Employee).where(Employee.organization_id == p.organization_id)
    if department is not None:
        query = query.where(Employee.department == department)
    if status is not None:
        query = query.where(Employee.status == status)
    if search is not None:
        query = query.where(func.lower(Employee.name).contains(search.lower(), autoescape=True))
    records = db.scalars(
        ordered(query, Employee, sort_by, direction, {"id", "name", "created_at"})
        .offset(offset)
        .limit(limit)
    ).all()
    return [employee_view(db, record) for record in records]


@router.get("/employees/{employee_id}", response_model=EmployeeOutput)
def employee(
    employee_id: UUID, db: DB, p: Annotated[Principal, Depends(permission("employee.read"))]
):
    record = scoped(db, Employee, p, str(employee_id))
    audit(db, p, "employee.read", record.id)
    return employee_view(db, record)


@router.post("/hr/payroll", response_model=PayrollOutput, status_code=201)
def payroll(
    data: PayrollInput, db: DB, p: Annotated[Principal, Depends(permission("payroll.write"))]
):
    employee_record = scoped(db, Employee, p, str(data.employee_id))
    if employee_record.status == "offboarded":
        raise HTTPException(
            409, "Offboarded employee payroll requires a separately reviewed final settlement"
        )
    governed = db.scalar(
        select(EmploymentTerms.id)
        .where(
            EmploymentTerms.organization_id == p.organization_id,
            EmploymentTerms.employee_id == employee_record.id,
            EmploymentTerms.effective_on <= date.fromisoformat(data.period + "-01"),
        )
        .limit(1)
    )
    if governed:
        raise HTTPException(
            409, "Use reviewed salary-policy computation for this employee's payroll"
        )
    record = Payroll(
        id=identifier(),
        organization_id=p.organization_id,
        **data.model_dump(exclude={"employee_id"}),
        employee_id=str(data.employee_id),
        net=payroll_net(data.gross, data.deductions),
    )
    db.add(record)
    emit(db, p, "payroll.recorded", record.id)
    return record


@router.post("/projects", response_model=ProjectOutput, status_code=201)
def project_create(
    data: ProjectInput, db: DB, p: Annotated[Principal, Depends(permission("project.create"))]
):
    record = Project(
        id=identifier(),
        organization_id=p.organization_id,
        proposer_id=p.user_id,
        approval_policy=snapshot(db, p.organization_id),
        **data.model_dump(),
    )
    db.add(record)
    db.flush()
    emit(db, p, "project.created", record.id)
    db.add(
        ProjectMember(
            organization_id=p.organization_id,
            project_id=record.id,
            user_id=p.user_id,
            manager=p.role == "senior_developer",
        )
    )
    return record


@router.get("/projects", response_model=list[ProjectOutput])
def projects(
    db: DB,
    p: Annotated[Principal, Depends(permission("project.read"))],
    limit: Limit = 50,
    offset: Offset = 0,
    status: Literal["proposed", "reviewed", "approved", "rejected"] | None = None,
    search: Annotated[str | None, Query(min_length=1, max_length=100)] = None,
    sort_by: Literal["id", "name", "created_at", "status"] = "id",
    direction: Literal["asc", "desc"] = "asc",
):
    query = select(Project).where(Project.organization_id == p.organization_id)
    if p.role != "owner":
        member = db.get(Membership, (p.organization_id, p.user_id))
        proposer_scope = Project.proposer_id == p.user_id
        if member is not None and member.access_not_before is not None:
            proposer_scope = proposer_scope & (Project.created_at > member.access_not_before)
        query = query.where(
            proposer_scope
            | Project.id.in_(
                select(ProjectMember.project_id).where(
                    ProjectMember.organization_id == p.organization_id,
                    ProjectMember.user_id == p.user_id,
                )
            )
        )
    if status is not None:
        query = query.where(Project.status == status)
    if search is not None:
        query = query.where(func.lower(Project.name).contains(search.lower(), autoescape=True))
    return db.scalars(
        ordered(query, Project, sort_by, direction, {"id", "name", "created_at", "status"})
        .offset(offset)
        .limit(limit)
    ).all()


@router.get("/projects/{project_id}", response_model=ProjectOutput)
def project_get(
    project_id: UUID, db: DB, p: Annotated[Principal, Depends(permission("project.read"))]
):
    return project_access(db, p, str(project_id))


@router.post("/projects/{project_id}/decision", response_model=ProjectOutput)
def project_decision(project_id: UUID, data: ProjectDecision, p: P, db: DB):
    if data.decision == "reviewed":
        return review(db, p, str(project_id))
    p.require("project.review" if data.decision == "reviewed" else "project.approve")
    record = scoped(db, Project, p, str(project_id), lock=True)
    if record.proposer_id == p.user_id:
        raise HTTPException(403, "Self-review is forbidden")
    allowed = {
        "reviewed": {"proposed"},
        "approved": {"reviewed"},
        "rejected": {"proposed", "reviewed"},
    }
    if record.status not in allowed[data.decision]:
        raise HTTPException(409, "Invalid project transition")
    if (
        data.decision == "approved"
        and len(eligible_reviewers(db, record))
        < effective_policy(record)["required_senior_reviews"]
    ):
        raise HTTPException(
            409, "Active independent senior reviews are required before owner approval"
        )
    record.status = data.decision
    emit(db, p, "project." + data.decision, record.id)
    return record


@router.post("/tasks", response_model=TaskOutput, status_code=201)
def task_create(
    data: TaskInput, db: DB, p: Annotated[Principal, Depends(permission("task.manage"))]
):
    project = project_access(db, p, str(data.project_id), manager=True)
    if project.status != "approved":
        raise HTTPException(403, "Approved project under your management required")
    member = db.get(Membership, (p.organization_id, str(data.assignee_id)))
    if (
        not member
        or not member.active
        or member.role not in {"senior_developer", "junior_developer"}
    ):
        raise HTTPException(422, "Active developer assignee required")
    project_access(db, Principal(member.user_id, p.organization_id, member.role), project.id)
    record = Task(
        id=identifier(),
        organization_id=p.organization_id,
        project_id=str(data.project_id),
        assignee_id=str(data.assignee_id),
        title=data.title,
    )
    db.add(record)
    db.flush()
    emit(db, p, "task.created", record.id)
    return record


@router.get("/repositories/{repository_id}")
def repository_get(
    repository_id: UUID, db: DB, p: Annotated[Principal, Depends(permission("repository.read"))]
):
    record = repository_access(db, p, str(repository_id))
    return {"id": record.id, "full_name": record.full_name, "enabled": record.enabled}


@router.get("/findings/{finding_id}", response_model=FindingOutput)
def finding_get(
    finding_id: UUID, db: DB, p: Annotated[Principal, Depends(permission("finding.read"))]
):
    record = scoped(db, Finding, p, str(finding_id))
    repository_access(db, p, record.repository_id)
    return record


@router.post("/vader/events", response_model=EventOutput, status_code=201)
def event_ingest(
    data: EventInput, db: DB, p: Annotated[Principal, Depends(permission("security.ingest"))]
):
    return ingest(db, p, data)


@router.get("/vader/events", response_model=list[SecurityEventOutput])
def events(
    db: DB,
    p: Annotated[Principal, Depends(permission("security.read"))],
    limit: Limit = 50,
    offset: Offset = 0,
    category: EventCategory | None = None,
    actor_id: Annotated[str | None, Query(min_length=1, max_length=100)] = None,
    synthetic: bool | None = None,
    source_kind: SourceKind | None = None,
    reported_severity: EventSeverity | None = None,
):
    p = security_authority(db, p)
    query = select(SecurityEvent).where(SecurityEvent.organization_id == p.organization_id)
    if category is not None:
        query = query.where(SecurityEvent.category == category)
    if actor_id is not None:
        query = query.where(SecurityEvent.actor_id == actor_id)
    if synthetic is not None:
        query = query.where(SecurityEvent.synthetic == synthetic)
    if source_kind is not None:
        query = query.where(SecurityEvent.context["source"]["kind"].as_string() == source_kind)
    if reported_severity is not None:
        query = query.where(
            SecurityEvent.context["reported_severity"].as_string() == reported_severity
        )
    audit(db, p, "security.events.read", p.organization_id)
    return db.scalars(
        query.order_by(SecurityEvent.occurred_at, SecurityEvent.id).offset(offset).limit(limit)
    ).all()


@router.get("/vader/events/{event_id}", response_model=SecurityEventOutput)
def event_get(
    event_id: UUID, db: DB, p: Annotated[Principal, Depends(permission("security.read"))]
):
    p = security_authority(db, p)
    record = scoped(db, SecurityEvent, p, str(event_id))
    audit(db, p, "security.event.read", record.id)
    return record


@router.get("/vader/anomalies", response_model=list[AnomalyOutput])
def anomalies(
    db: DB,
    p: Annotated[Principal, Depends(permission("security.read"))],
    limit: Limit = 50,
    offset: Offset = 0,
):
    p = security_authority(db, p)
    audit(db, p, "security.anomalies.read", p.organization_id)
    return db.scalars(
        select(Anomaly)
        .where(Anomaly.organization_id == p.organization_id)
        .order_by(Anomaly.id)
        .offset(offset)
        .limit(limit)
    ).all()


@router.get("/vader/incidents", response_model=list[IncidentOutput])
def incidents(
    db: DB,
    p: Annotated[Principal, Depends(permission("security.read"))],
    limit: Limit = 50,
    offset: Offset = 0,
    status: Literal["open", "triaged", "contained", "resolved", "false_positive"] | None = None,
    synthetic: bool | None = None,
    minimum_risk: Annotated[int, Query(ge=0, le=100)] = 0,
    sort_by: Literal["id", "created_at", "risk"] = "id",
    direction: Literal["asc", "desc"] = "asc",
):
    p = security_authority(db, p)
    audit(db, p, "security.incidents.read", p.organization_id)
    query = select(Incident).where(
        Incident.organization_id == p.organization_id, Incident.risk >= minimum_risk
    )
    if status is not None:
        query = query.where(Incident.status == status)
    if synthetic is not None:
        query = query.where(Incident.synthetic == synthetic)
    return db.scalars(
        ordered(query, Incident, sort_by, direction, {"id", "created_at", "risk"})
        .offset(offset)
        .limit(limit)
    ).all()


@router.get("/vader/incidents/{incident_id}", response_model=IncidentOutput)
def incident_get(
    incident_id: UUID, db: DB, p: Annotated[Principal, Depends(permission("security.read"))]
):
    p = security_authority(db, p)
    record = scoped(db, Incident, p, str(incident_id))
    audit(db, p, "security.incident.read", record.id)
    return record


@router.get("/vader/incidents/{incident_id}/graph")
def incident_graph(
    incident_id: UUID, db: DB, p: Annotated[Principal, Depends(permission("security.read"))]
):
    p = security_authority(db, p)
    record = scoped(db, Incident, p, str(incident_id))
    audit(db, p, "security.incident.graph.read", record.id)
    events = db.scalars(
        select(SecurityEvent)
        .where(
            SecurityEvent.organization_id == p.organization_id,
            SecurityEvent.id.in_(record.event_ids),
        )
        .order_by(SecurityEvent.occurred_at, SecurityEvent.id)
    ).all()
    return {
        "incident_id": record.id,
        "nodes": [
            {
                "id": e.id,
                "category": e.category,
                "timestamp": as_utc(e.occurred_at).isoformat(),
            }
            for e in events
        ],
        "edges": [
            {"source": a.id, "target": b.id, "relation": "same_actor_temporal_proximity"}
            for a, b in zip(events, events[1:], strict=False)
        ],
        "explanation": record.explanation,
        "correlation_snapshot": record.correlation_snapshot,
    }


@router.post("/vader/simulator/{run_id}", response_model=list[EventOutput])
def simulation(
    run_id: UUID, db: DB, p: Annotated[Principal, Depends(permission("security.ingest"))]
):
    return simulate(db, p, str(run_id))


@router.post("/vader/responses", response_model=ResponseOutput, status_code=201)
def response_propose(
    data: ResponseInput, db: DB, p: Annotated[Principal, Depends(permission("response.propose"))]
):
    scoped(db, Incident, p, str(data.incident_id))
    record = ResponseAction(
        id=identifier(),
        organization_id=p.organization_id,
        incident_id=str(data.incident_id),
        action=data.action,
        proposed_by=p.user_id,
    )
    db.add(record)
    db.flush()
    emit(db, p, "incident.response.proposed", record.id)
    return record


@router.post("/vader/responses/{response_id}/approve", response_model=ResponseOutput)
def response_approve(
    response_id: UUID, db: DB, p: Annotated[Principal, Depends(permission("response.approve"))]
):
    record = scoped(db, ResponseAction, p, str(response_id), lock=True)
    if record.status != "proposed":
        raise HTTPException(409, "Response is no longer proposed")
    if record.proposed_by == p.user_id:
        raise HTTPException(403, "Independent approval required")
    record.approved_by = p.user_id
    record.status = "simulated"
    emit(db, p, "incident.response.approved", record.id)
    return record


@router.post("/trust/events", status_code=201)
def trust_event(
    data: TrustInput, db: DB, p: Annotated[Principal, Depends(permission("trust.review"))]
):
    member = db.get(Membership, (p.organization_id, str(data.user_id)))
    if not member or member.role in {"owner", "hr"}:
        raise HTTPException(422, "Trust scoring excludes Owner and HR")
    record = TrustEvent(
        id=identifier(),
        organization_id=p.organization_id,
        user_id=str(data.user_id),
        reference=data.reference,
        delta=data.delta,
        reason=data.reason,
        reviewed_by=p.user_id,
    )
    db.add(record)
    emit(db, p, "trust.review.recorded", record.id)
    return {"id": record.id}


@router.get("/trust/{user_id}")
def trust_score(user_id: UUID, p: P, db: DB):
    if str(user_id) != p.user_id:
        p.require("trust.review")
    member = db.get(Membership, (p.organization_id, str(user_id)))
    if not member or member.role in {"owner", "hr"}:
        raise HTTPException(404, "Scored employee not found")
    events = db.scalars(
        select(TrustEvent)
        .where(TrustEvent.organization_id == p.organization_id, TrustEvent.user_id == str(user_id))
        .order_by(TrustEvent.created_at, TrustEvent.id)
    ).all()
    score = 20
    for event in events:
        score = max(0, min(50, score + event.delta))
    return {
        "score": score,
        "stars": score // 10,
        "decision_support_only": True,
        "events": [{"id": e.id, "delta": e.delta, "reason": e.reason} for e in events],
    }


@router.get("/ai/incidents/{incident_id}", response_model=SummaryOutput)
def incident_summary(
    incident_id: UUID, db: DB, p: Annotated[Principal, Depends(permission("security.read"))]
):
    record = scoped(db, Incident, p, str(incident_id))
    audit(db, p, "ai.local_summary", record.id)
    return SummaryOutput(
        incident_id=record.id,
        summary=f"{len(record.event_ids)} correlated events; policy risk {record.risk}/100. {record.explanation}",
        limitations=[
            "Deterministic template; no external LLM used",
            "Human investigation required; no enforcement decision",
        ],
    )


@router.get("/audit")
def audit_list(
    db: DB,
    p: Annotated[Principal, Depends(permission("audit.read"))],
    limit: Limit = 50,
    offset: Offset = 0,
):
    rows = db.scalars(
        select(AuditLog)
        .where(AuditLog.organization_id == p.organization_id)
        .order_by(AuditLog.created_at, AuditLog.id)
        .offset(offset)
        .limit(limit)
    ).all()
    return [
        {
            "id": row.id,
            "actor_id": row.actor_id,
            "action": row.action,
            "target_id": row.target_id,
            "outcome": row.outcome,
            "timestamp": row.created_at,
        }
        for row in rows
    ]
