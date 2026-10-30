import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


def identifier() -> str:
    return str(uuid.uuid4())


def now() -> datetime:
    return datetime.now(UTC)


class Organization(Base):
    __tablename__ = "organizations"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=identifier)
    name: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(default="active")
    verification_status: Mapped[str] = mapped_column(default="unverified")
    domain: Mapped[str | None] = mapped_column(String(253), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class IdentitySession(Base):
    """Self-owned account security metadata; RLS follows verified user, not an employer."""

    __tablename__ = "identity_sessions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=identifier)
    user_id: Mapped[str] = mapped_column(String(36), index=True)
    provider_session_id: Mapped[str] = mapped_column(String(36))
    client_hint: Mapped[str] = mapped_column(String(200))
    ip_digest: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    last_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revocation_reason: Mapped[str | None] = mapped_column(String(40))
    __table_args__ = (UniqueConstraint("user_id", "provider_session_id"),)


class Membership(Base):
    __tablename__ = "memberships"
    organization_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    email: Mapped[str] = mapped_column(String(254))
    role: Mapped[str] = mapped_column(String(30))
    active: Mapped[bool] = mapped_column(default=True)
    access_not_before: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        Index("ix_memberships_user_org", "user_id", "organization_id"),
        ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        CheckConstraint(
            "role IN ('owner','hr','senior_developer','junior_developer','security_analyst')"
        ),
        UniqueConstraint("organization_id", "email"),
    )


class DomainChallenge(Base):
    __tablename__ = "domain_challenges"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=identifier)
    organization_id: Mapped[str] = mapped_column(String(36), index=True)
    domain: Mapped[str] = mapped_column(String(253))
    token_hash: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    attempts: Mapped[int] = mapped_column(default=0)
    status: Mapped[str] = mapped_column(default="pending")
    __table_args__ = (ForeignKeyConstraint(["organization_id"], ["organizations.id"]),)


class TenantRow:
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=identifier)
    organization_id: Mapped[str] = mapped_column(String(36), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Invitation(TenantRow, Base):
    __tablename__ = "invitations"
    email: Mapped[str] = mapped_column(String(254))
    role: Mapped[str] = mapped_column(String(30))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    creator_id: Mapped[str] = mapped_column(String(36))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(default="pending")
    __table_args__ = (ForeignKeyConstraint(["organization_id"], ["organizations.id"]),)


class Employee(TenantRow, Base):
    __tablename__ = "employees"
    user_id: Mapped[str] = mapped_column(String(36))
    name: Mapped[str] = mapped_column(String(200))
    department: Mapped[str] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(default="onboarding")
    verification_status: Mapped[str] = mapped_column(default="pending")
    __table_args__ = (
        UniqueConstraint("organization_id", "id"),
        UniqueConstraint("organization_id", "user_id"),
        ForeignKeyConstraint(
            ["organization_id", "user_id"], ["memberships.organization_id", "memberships.user_id"]
        ),
    )


class Payroll(TenantRow, Base):
    __tablename__ = "payroll"
    employee_id: Mapped[str] = mapped_column(String(36))
    period: Mapped[str] = mapped_column(String(7))
    currency: Mapped[str] = mapped_column(String(3))
    gross: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    deductions: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    net: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    __table_args__ = (
        Index("uq_payroll_org_id", "organization_id", "id", unique=True),
        UniqueConstraint("organization_id", "employee_id", "period"),
        ForeignKeyConstraint(
            ["organization_id", "employee_id"], ["employees.organization_id", "employees.id"]
        ),
        CheckConstraint("gross >= 0 AND deductions >= 0 AND net >= 0 AND net = gross - deductions"),
    )


class Project(TenantRow, Base):
    __tablename__ = "projects"
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(String(4000))
    proposer_id: Mapped[str] = mapped_column(String(36))
    status: Mapped[str] = mapped_column(default="proposed")
    approval_policy: Mapped[dict | None] = mapped_column(JSON)
    __table_args__ = (
        UniqueConstraint("organization_id", "id"),
        ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        CheckConstraint("status IN ('proposed','reviewed','approved','rejected')"),
    )


class ProjectApprovalPolicy(TenantRow, Base):
    __tablename__ = "project_approval_policies"
    version: Mapped[int]
    required_senior_reviews: Mapped[int]
    reviewers_must_be_members: Mapped[bool] = mapped_column(default=False)
    __table_args__ = (
        ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        UniqueConstraint("organization_id", "version"),
        CheckConstraint("version > 0 AND required_senior_reviews BETWEEN 1 AND 5"),
    )


class ProjectReview(TenantRow, Base):
    __tablename__ = "project_reviews"
    project_id: Mapped[str] = mapped_column(String(36))
    reviewer_id: Mapped[str] = mapped_column(String(36))
    comment: Mapped[str] = mapped_column(String(2000), default="")
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "project_id"], ["projects.organization_id", "projects.id"]
        ),
        ForeignKeyConstraint(
            ["organization_id", "reviewer_id"],
            ["memberships.organization_id", "memberships.user_id"],
        ),
        UniqueConstraint("organization_id", "project_id", "reviewer_id"),
    )


class Task(TenantRow, Base):
    __tablename__ = "tasks"
    project_id: Mapped[str] = mapped_column(String(36))
    assignee_id: Mapped[str] = mapped_column(String(36))
    title: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(default="todo")
    __table_args__ = (
        Index("uq_tasks_org_id", "organization_id", "id", unique=True),
        ForeignKeyConstraint(
            ["organization_id", "project_id"], ["projects.organization_id", "projects.id"]
        ),
        ForeignKeyConstraint(
            ["organization_id", "assignee_id"],
            ["memberships.organization_id", "memberships.user_id"],
        ),
    )


class Repository(TenantRow, Base):
    __tablename__ = "repositories"
    full_name: Mapped[str] = mapped_column(String(200))
    installation_id: Mapped[int]
    enabled: Mapped[bool] = mapped_column(default=False)
    __table_args__ = (
        UniqueConstraint("organization_id", "id"),
        UniqueConstraint("organization_id", "full_name"),
        ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
    )


class FindingIdentity(TenantRow, Base):
    __tablename__ = "finding_identities"
    repository_id: Mapped[str] = mapped_column(String(36))
    fingerprint: Mapped[str] = mapped_column(String(64))
    algorithm_version: Mapped[str] = mapped_column(String(50))
    match_metadata: Mapped[dict] = mapped_column(JSON)
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "repository_id"],
            ["repositories.organization_id", "repositories.id"],
        ),
        UniqueConstraint(
            "organization_id",
            "repository_id",
            "fingerprint",
            name="uq_finding_identity_fingerprint",
        ),
        UniqueConstraint(
            "organization_id", "repository_id", "id", name="uq_finding_identity_scope"
        ),
        CheckConstraint("length(fingerprint)=64", name="ck_finding_identity_fingerprint_length"),
        Index("ix_finding_identity_org_repository", "organization_id", "repository_id"),
    )


class Finding(TenantRow, Base):
    __tablename__ = "findings"
    repository_id: Mapped[str] = mapped_column(String(36))
    scanner: Mapped[str] = mapped_column(String(30))
    rule_id: Mapped[str] = mapped_column(String(200))
    severity: Mapped[str] = mapped_column(String(20))
    file_path: Mapped[str] = mapped_column(String(500))
    line: Mapped[int]
    status: Mapped[str] = mapped_column(default="open")
    column: Mapped[int | None]
    dependency: Mapped[dict | None] = mapped_column(JSON)
    scan_job_id: Mapped[str | None] = mapped_column(String(36))
    commit_sha: Mapped[str | None] = mapped_column(String(40))
    identity_id: Mapped[str | None] = mapped_column(String(36))
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "repository_id", "identity_id"],
            [
                "finding_identities.organization_id",
                "finding_identities.repository_id",
                "finding_identities.id",
            ],
            name="fk_finding_identity_scope",
        ),
        Index(
            "ix_finding_org_repository_identity", "organization_id", "repository_id", "identity_id"
        ),
        ForeignKeyConstraint(
            ["organization_id", "repository_id", "scan_job_id", "commit_sha"],
            [
                "scan_jobs.organization_id",
                "scan_jobs.repository_id",
                "scan_jobs.id",
                "scan_jobs.commit_sha",
            ],
            name="fk_finding_scan_commit",
        ),
        CheckConstraint(
            "(scan_job_id IS NULL AND commit_sha IS NULL) OR (scan_job_id IS NOT NULL AND commit_sha IS NOT NULL)",
            name="ck_finding_provenance_pair",
        ),
        CheckConstraint(
            "commit_sha IS NULL OR length(commit_sha)=40", name="ck_finding_commit_length"
        ),
        CheckConstraint('"column" IS NULL OR "column">0', name="ck_finding_column_positive"),
        Index("ix_finding_org_repository_scan", "organization_id", "repository_id", "scan_job_id"),
        ForeignKeyConstraint(
            ["organization_id", "repository_id"],
            ["repositories.organization_id", "repositories.id"],
        ),
    )


class SecurityEvent(TenantRow, Base):
    __tablename__ = "security_events"
    source_id: Mapped[str] = mapped_column(String(150))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    actor_id: Mapped[str] = mapped_column(String(100))
    category: Mapped[str] = mapped_column(String(50))
    action: Mapped[str] = mapped_column(String(80))
    result: Mapped[str] = mapped_column(String(30))
    count: Mapped[int] = mapped_column(default=1)
    synthetic: Mapped[bool] = mapped_column(default=False)
    session_id: Mapped[str | None] = mapped_column(String(100))
    resource_id: Mapped[str | None] = mapped_column(String(100))
    context: Mapped[dict] = mapped_column(JSON, default=dict)
    __table_args__ = (
        ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        UniqueConstraint("organization_id", "source_id"),
        UniqueConstraint("organization_id", "id"),
        Index("ix_event_actor_time", "organization_id", "actor_id", "occurred_at"),
        Index("ix_event_org_time_id", "organization_id", "occurred_at", "id"),
        Index("ix_event_org_category_time", "organization_id", "category", "occurred_at", "id"),
    )


class Anomaly(TenantRow, Base):
    __tablename__ = "anomalies"
    event_id: Mapped[str] = mapped_column(String(36))
    rule: Mapped[str] = mapped_column(String(80))
    weight: Mapped[int]
    explanation: Mapped[str] = mapped_column(String(500))
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "event_id"],
            ["security_events.organization_id", "security_events.id"],
        ),
        UniqueConstraint("organization_id", "event_id", "rule"),
    )


class Incident(TenantRow, Base):
    __tablename__ = "incidents"
    actor_id: Mapped[str] = mapped_column(String(100))
    fingerprint: Mapped[str] = mapped_column(String(64))
    event_ids: Mapped[list[str]] = mapped_column(JSON)
    risk: Mapped[int]
    explanation: Mapped[str] = mapped_column(String(1000))
    status: Mapped[str] = mapped_column(default="open")
    synthetic: Mapped[bool] = mapped_column(default=False)
    correlation_policy_id: Mapped[str | None] = mapped_column(String(36))
    correlation_snapshot: Mapped[dict | None] = mapped_column(JSON)
    __table_args__ = (
        ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        ForeignKeyConstraint(
            ["organization_id", "correlation_policy_id"],
            ["correlation_policies.organization_id", "correlation_policies.id"],
            name="fk_incident_correlation_policy",
        ),
        CheckConstraint(
            "correlation_policy_id IS NULL OR correlation_snapshot IS NOT NULL",
            name="ck_incident_correlation_snapshot",
        ),
        Index("ix_incident_org_correlation_policy", "organization_id", "correlation_policy_id"),
        UniqueConstraint("organization_id", "fingerprint"),
        UniqueConstraint("organization_id", "id"),
    )


class ResponseAction(TenantRow, Base):
    __tablename__ = "response_actions"
    incident_id: Mapped[str] = mapped_column(String(36))
    action: Mapped[str] = mapped_column(String(50))
    proposed_by: Mapped[str] = mapped_column(String(36))
    approved_by: Mapped[str | None] = mapped_column(String(36))
    status: Mapped[str] = mapped_column(default="proposed")
    mode: Mapped[str] = mapped_column(default="simulation")
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "incident_id"], ["incidents.organization_id", "incidents.id"]
        ),
    )


class TrustEvent(TenantRow, Base):
    __tablename__ = "trust_events"
    user_id: Mapped[str] = mapped_column(String(36))
    reference: Mapped[str] = mapped_column(String(100))
    delta: Mapped[int]
    reason: Mapped[str] = mapped_column(String(500))
    reviewed_by: Mapped[str] = mapped_column(String(36))
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "user_id"], ["memberships.organization_id", "memberships.user_id"]
        ),
        UniqueConstraint("organization_id", "reference"),
        CheckConstraint("delta BETWEEN -10 AND 10"),
    )


class AuditLog(TenantRow, Base):
    __tablename__ = "audit_logs"
    actor_id: Mapped[str] = mapped_column(String(36))
    action: Mapped[str] = mapped_column(String(100))
    target_id: Mapped[str] = mapped_column(String(100))
    outcome: Mapped[str] = mapped_column(default="success")
    __table_args__ = (ForeignKeyConstraint(["organization_id"], ["organizations.id"]),)


class Outbox(TenantRow, Base):
    __tablename__ = "outbox"
    topic: Mapped[str] = mapped_column(String(100))
    payload: Mapped[dict] = mapped_column(JSON)
    attempts: Mapped[int] = mapped_column(default=0)
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    status: Mapped[str] = mapped_column(default="pending")
    __table_args__ = (ForeignKeyConstraint(["organization_id"], ["organizations.id"]),)


class Delivery(TenantRow, Base):
    __tablename__ = "deliveries"
    message_id: Mapped[str] = mapped_column(String(36))
    consumer: Mapped[str] = mapped_column(String(100))
    __table_args__ = (
        ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        UniqueConstraint("organization_id", "message_id", "consumer"),
    )


class Department(TenantRow, Base):
    __tablename__ = "departments"
    name: Mapped[str] = mapped_column(String(100))
    __table_args__ = (
        UniqueConstraint("organization_id", "name"),
        ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
    )


class WebhookDelivery(TenantRow, Base):
    __tablename__ = "webhook_deliveries"
    provider: Mapped[str] = mapped_column(String(30), default="github")
    delivery_id: Mapped[str] = mapped_column(String(36))
    event: Mapped[str] = mapped_column(String(50))
    payload_digest: Mapped[str] = mapped_column(String(64))
    result: Mapped[dict] = mapped_column(JSON)
    __table_args__ = (
        ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        UniqueConstraint("organization_id", "provider", "delivery_id"),
        UniqueConstraint("organization_id", "provider", "payload_digest"),
    )


class LeaveRequest(TenantRow, Base):
    __tablename__ = "leave_requests"
    employee_id: Mapped[str] = mapped_column(String(36))
    starts_on: Mapped[date] = mapped_column(Date)
    ends_on: Mapped[date] = mapped_column(Date)
    reason: Mapped[str] = mapped_column(String(1000))
    status: Mapped[str] = mapped_column(default="pending")
    reviewed_by: Mapped[str | None] = mapped_column(String(36))
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "employee_id"], ["employees.organization_id", "employees.id"]
        ),
        CheckConstraint("ends_on >= starts_on"),
    )


class Complaint(TenantRow, Base):
    __tablename__ = "complaints"
    author_id: Mapped[str] = mapped_column(String(36))
    subject: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(String(4000))
    status: Mapped[str] = mapped_column(default="open")
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "author_id"], ["memberships.organization_id", "memberships.user_id"]
        ),
    )


class IntegrationAccount(TenantRow, Base):
    __tablename__ = "integration_accounts"
    user_id: Mapped[str] = mapped_column(String(36))
    provider: Mapped[str] = mapped_column(String(30))
    external_id: Mapped[str] = mapped_column(String(200))
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "user_id"], ["memberships.organization_id", "memberships.user_id"]
        ),
    )


class LifecyclePlan(TenantRow, Base):
    __tablename__ = "lifecycle_plans"
    employee_id: Mapped[str] = mapped_column(String(36))
    kind: Mapped[str] = mapped_column(String(30))
    snapshot: Mapped[dict] = mapped_column(JSON)
    proposed: Mapped[dict] = mapped_column(JSON)
    proposed_by: Mapped[str] = mapped_column(String(36))
    approved_by: Mapped[str | None] = mapped_column(String(36))
    status: Mapped[str] = mapped_column(default="proposed")
    history: Mapped[list] = mapped_column(JSON, default=list)
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "employee_id"], ["employees.organization_id", "employees.id"]
        ),
    )


class ProjectMember(TenantRow, Base):
    __tablename__ = "project_members"
    project_id: Mapped[str] = mapped_column(String(36))
    user_id: Mapped[str] = mapped_column(String(36))
    manager: Mapped[bool] = mapped_column(default=False)
    __table_args__ = (
        UniqueConstraint("organization_id", "project_id", "user_id"),
        ForeignKeyConstraint(
            ["organization_id", "project_id"], ["projects.organization_id", "projects.id"]
        ),
        ForeignKeyConstraint(
            ["organization_id", "user_id"], ["memberships.organization_id", "memberships.user_id"]
        ),
    )


class Sprint(TenantRow, Base):
    __tablename__ = "sprints"
    project_id: Mapped[str] = mapped_column(String(36))
    name: Mapped[str] = mapped_column(String(100))
    starts_on: Mapped[date] = mapped_column(Date)
    ends_on: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(default="planned")
    __table_args__ = (
        UniqueConstraint("organization_id", "id"),
        ForeignKeyConstraint(
            ["organization_id", "project_id"], ["projects.organization_id", "projects.id"]
        ),
        CheckConstraint("ends_on >= starts_on"),
    )


class TaskDetail(TenantRow, Base):
    __tablename__ = "task_details"
    task_id: Mapped[str] = mapped_column(String(36), unique=True)
    priority: Mapped[str] = mapped_column(default="normal")
    deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sprint_id: Mapped[str | None] = mapped_column(String(36))
    __table_args__ = (
        ForeignKeyConstraint(["organization_id", "task_id"], ["tasks.organization_id", "tasks.id"]),
        ForeignKeyConstraint(
            ["organization_id", "sprint_id"], ["sprints.organization_id", "sprints.id"]
        ),
    )


class AuditSeal(TenantRow, Base):
    __tablename__ = "audit_seals"
    audit_id: Mapped[str] = mapped_column(String(36), unique=True)
    position: Mapped[int]
    previous_hash: Mapped[str] = mapped_column(String(64))
    digest: Mapped[str] = mapped_column(String(64))
    __table_args__ = (
        UniqueConstraint("organization_id", "position"),
        ForeignKeyConstraint(["audit_id"], ["audit_logs.id"]),
        ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
    )


class ProjectComment(TenantRow, Base):
    __tablename__ = "project_comments"
    project_id: Mapped[str] = mapped_column(String(36))
    author_id: Mapped[str] = mapped_column(String(36))
    body: Mapped[str] = mapped_column(String(4000))
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "project_id"], ["projects.organization_id", "projects.id"]
        ),
    )


class RepositoryProject(TenantRow, Base):
    __tablename__ = "repository_projects"
    repository_id: Mapped[str] = mapped_column(String(36))
    project_id: Mapped[str] = mapped_column(String(36))
    __table_args__ = (
        UniqueConstraint("organization_id", "repository_id", "project_id"),
        ForeignKeyConstraint(
            ["organization_id", "repository_id"],
            ["repositories.organization_id", "repositories.id"],
        ),
        ForeignKeyConstraint(
            ["organization_id", "project_id"], ["projects.organization_id", "projects.id"]
        ),
    )


class ScanJob(TenantRow, Base):
    __tablename__ = "scan_jobs"
    repository_id: Mapped[str] = mapped_column(String(36))
    requested_by: Mapped[str] = mapped_column(String(36))
    request_key: Mapped[str] = mapped_column(String(100))
    commit_sha: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(default="queued")
    attempts: Mapped[int] = mapped_column(default=0)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    report: Mapped[dict] = mapped_column(JSON, default=dict)
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "repository_id",
            "id",
            "commit_sha",
            name="uq_scan_finding_provenance",
        ),
        UniqueConstraint("organization_id", "request_key"),
        ForeignKeyConstraint(
            ["organization_id", "repository_id"],
            ["repositories.organization_id", "repositories.id"],
        ),
    )


class IdentityDocument(TenantRow, Base):
    __tablename__ = "identity_documents"
    employee_id: Mapped[str] = mapped_column(String(36))
    storage_key: Mapped[str] = mapped_column(String(300), unique=True)
    media_type: Mapped[str] = mapped_column(String(100))
    digest: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(default="pending_hr")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    reviewed_by: Mapped[str | None] = mapped_column(String(36))
    ocr_status: Mapped[str] = mapped_column(String(30), default="not_configured")
    ocr_attempts: Mapped[int] = mapped_column(default=0)
    ocr_lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ocr_ciphertext: Mapped[str | None] = mapped_column(Text)
    ocr_error_code: Mapped[str | None] = mapped_column(String(60))
    ocr_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        UniqueConstraint("organization_id", "id", name="uq_identity_document_tenant_id"),
        Index("ix_identity_ocr_queue", "organization_id", "ocr_status", "ocr_lease_until"),
        ForeignKeyConstraint(
            ["organization_id", "employee_id"], ["employees.organization_id", "employees.id"]
        ),
    )


class DocumentHold(TenantRow, Base):
    __tablename__ = "document_holds"
    document_id: Mapped[str] = mapped_column(String(36))
    request_key: Mapped[str] = mapped_column(String(36))
    reason_code: Mapped[str] = mapped_column(String(30))
    placed_by: Mapped[str] = mapped_column(String(36))
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    released_by: Mapped[str | None] = mapped_column(String(36))
    release_reason: Mapped[str | None] = mapped_column(String(30))
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "document_id"],
            ["identity_documents.organization_id", "identity_documents.id"],
        ),
        ForeignKeyConstraint(
            ["organization_id", "placed_by"], ["memberships.organization_id", "memberships.user_id"]
        ),
        ForeignKeyConstraint(
            ["organization_id", "released_by"],
            ["memberships.organization_id", "memberships.user_id"],
        ),
        UniqueConstraint("organization_id", "request_key", name="uq_document_hold_request"),
        Index("ix_document_hold_active", "organization_id", "document_id", "released_at"),
        Index(
            "uq_document_active_hold",
            "organization_id",
            "document_id",
            unique=True,
            postgresql_where=text("released_at IS NULL"),
            sqlite_where=text("released_at IS NULL"),
        ),
        CheckConstraint("length(request_key)=36", name="ck_document_hold_request"),
        CheckConstraint(
            "reason_code IN ('dispute','investigation','regulatory','other')",
            name="ck_document_hold_reason",
        ),
        CheckConstraint(
            "(released_at IS NULL AND released_by IS NULL AND release_reason IS NULL) OR "
            "(released_at IS NOT NULL AND released_by IS NOT NULL AND released_by != placed_by "
            "AND released_at >= created_at AND release_reason IS NOT NULL AND release_reason IN ('resolved','entered_in_error','other'))",
            name="ck_document_hold_release",
        ),
    )


class CostRecord(TenantRow, Base):
    __tablename__ = "cost_records"
    period: Mapped[str] = mapped_column(String(7))
    department: Mapped[str] = mapped_column(String(100))
    category: Mapped[str] = mapped_column(String(30))
    currency: Mapped[str] = mapped_column(String(3))
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    source: Mapped[str] = mapped_column(default="manual")
    request_key: Mapped[str | None] = mapped_column(String(36))
    request_digest: Mapped[str | None] = mapped_column(String(64))
    recorded_by: Mapped[str | None] = mapped_column(String(36))
    billing_provider: Mapped[str | None] = mapped_column(String(10))
    usage_quantity: Mapped[Decimal | None] = mapped_column(Numeric(20, 6))
    usage_unit: Mapped[str | None] = mapped_column(String(20))
    __table_args__ = (
        ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        ForeignKeyConstraint(
            ["organization_id", "recorded_by"],
            ["memberships.organization_id", "memberships.user_id"],
            name="fk_cost_actor_tenant",
        ),
        UniqueConstraint("organization_id", "request_key", name="uq_cost_request_key"),
        CheckConstraint(
            "(request_key IS NULL AND request_digest IS NULL AND recorded_by IS NULL) OR (request_key IS NOT NULL AND request_digest IS NOT NULL AND recorded_by IS NOT NULL)",
            name="ck_cost_receipt_complete",
        ),
        CheckConstraint(
            "request_key IS NULL OR length(request_key)=36", name="ck_cost_request_key_length"
        ),
        CheckConstraint(
            "request_digest IS NULL OR length(request_digest)=64", name="ck_cost_digest_length"
        ),
        CheckConstraint("amount >= 0"),
        CheckConstraint(
            "(usage_quantity IS NULL AND usage_unit IS NULL) OR (usage_quantity IS NOT NULL AND usage_unit IS NOT NULL)",
            name="ck_cost_usage_pair",
        ),
        CheckConstraint(
            "usage_quantity IS NULL OR usage_quantity >= 0", name="ck_cost_usage_nonnegative"
        ),
        Index("ix_cost_org_currency_period", "organization_id", "currency", "period", "department"),
    )


class Budget(TenantRow, Base):
    __tablename__ = "budgets"
    period: Mapped[str] = mapped_column(String(7))
    currency: Mapped[str] = mapped_column(String(3))
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    __table_args__ = (
        ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        UniqueConstraint("organization_id", "period", "currency"),
        CheckConstraint("amount >= 0"),
    )


class CorrelationPolicy(TenantRow, Base):
    __tablename__ = "correlation_policies"
    version: Mapped[int]
    created_by: Mapped[str] = mapped_column(String(36))
    algorithm_version: Mapped[str] = mapped_column(String(40))
    configuration: Mapped[dict] = mapped_column(JSON)
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "created_by"],
            ["memberships.organization_id", "memberships.user_id"],
        ),
        UniqueConstraint("organization_id", "id"),
        UniqueConstraint("organization_id", "version"),
        CheckConstraint("version > 0", name="ck_correlation_policy_version"),
    )


class DetectionPolicy(TenantRow, Base):
    __tablename__ = "detection_policies"
    thresholds: Mapped[dict] = mapped_column(JSON)
    __table_args__ = (
        ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        UniqueConstraint("organization_id"),
    )


class CloudAssessment(TenantRow, Base):
    __tablename__ = "cloud_assessments"
    provider: Mapped[str] = mapped_column(default="aws")
    findings: Mapped[list] = mapped_column(JSON)
    partial: Mapped[bool] = mapped_column(default=False)
    errors: Mapped[list | None] = mapped_column(JSON)
    coverage: Mapped[list | None] = mapped_column(JSON)
    limitations: Mapped[list | None] = mapped_column(JSON)
    normalized_context: Mapped[dict | None] = mapped_column(JSON(none_as_null=True))
    __table_args__ = (
        ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        Index("uq_cloud_assessments_org_id", "organization_id", "id", unique=True),
    )


class CloudAssessmentJob(TenantRow, Base):
    __tablename__ = "cloud_assessment_jobs"
    requested_by: Mapped[str] = mapped_column(String(36))
    request_key: Mapped[str] = mapped_column(String(100))
    provider: Mapped[str] = mapped_column(String(20), default="aws")
    status: Mapped[str] = mapped_column(String(20), default="queued")
    attempts: Mapped[int] = mapped_column(default=0)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    assessment_id: Mapped[str | None] = mapped_column(String(36))
    error_code: Mapped[str | None] = mapped_column(String(50))
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "requested_by"],
            ["memberships.organization_id", "memberships.user_id"],
        ),
        ForeignKeyConstraint(
            ["organization_id", "assessment_id"],
            ["cloud_assessments.organization_id", "cloud_assessments.id"],
        ),
        UniqueConstraint("organization_id", "request_key"),
        CheckConstraint("status IN ('queued','running','completed','dead_letter','cancelled')"),
        CheckConstraint("attempts >= 0 AND attempts <= 3"),
    )


class BillingCollection(TenantRow, Base):
    __tablename__ = "billing_collections"
    requested_by: Mapped[str] = mapped_column(String(36))
    requested_session_id: Mapped[str | None] = mapped_column(String(36))
    requested_aal: Mapped[str] = mapped_column(String(4))
    request_key: Mapped[str] = mapped_column(String(36))
    period: Mapped[str] = mapped_column(String(7))
    provider_account_id: Mapped[str] = mapped_column(String(12))
    binding_revision: Mapped[str] = mapped_column(String(64))
    synthetic: Mapped[bool] = mapped_column(default=False)
    status: Mapped[str] = mapped_column(String(20), default="queued")
    attempts: Mapped[int] = mapped_column(default=0)
    dispatch_token: Mapped[str | None] = mapped_column(String(36))
    dispatched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_code: Mapped[str | None] = mapped_column(String(50))
    report: Mapped[dict | None] = mapped_column(JSON(none_as_null=True))
    __table_args__ = (
        ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        ForeignKeyConstraint(
            ["organization_id", "requested_by"],
            ["memberships.organization_id", "memberships.user_id"],
        ),
        ForeignKeyConstraint(
            ["requested_by", "requested_session_id"],
            ["identity_sessions.user_id", "identity_sessions.provider_session_id"],
        ),
        UniqueConstraint("organization_id", "request_key", name="uq_billing_collection_request"),
        Index("ix_billing_collection_queue", "organization_id", "status", "created_at"),
        CheckConstraint(
            "status IN ('queued','running','completed','failed','ambiguous','cancelled')",
            name="ck_billing_collection_status",
        ),
        CheckConstraint("attempts >= 0 AND attempts <= 1", name="ck_billing_collection_attempts"),
        CheckConstraint("requested_aal IN ('aal1','aal2')", name="ck_billing_collection_aal"),
        CheckConstraint(
            "length(request_key)=36 AND length(binding_revision)=64 AND length(provider_account_id)=12 AND length(period)=7",
            name="ck_billing_collection_identity",
        ),
        CheckConstraint(
            "(dispatch_token IS NULL) = (dispatched_at IS NULL)",
            name="ck_billing_collection_dispatch_pair",
        ),
        CheckConstraint(
            "(attempts=0 AND dispatch_token IS NULL) OR (attempts=1 AND dispatch_token IS NOT NULL)",
            name="ck_billing_collection_dispatch_attempt",
        ),
        CheckConstraint(
            "(status='queued' AND attempts=0 AND lease_until IS NULL AND finished_at IS NULL) OR (status='running' AND attempts=1 AND lease_until IS NOT NULL AND finished_at IS NULL) OR (status IN ('completed','failed','ambiguous','cancelled') AND lease_until IS NULL AND finished_at IS NOT NULL)",
            name="ck_billing_collection_lifecycle",
        ),
        CheckConstraint(
            "(status='completed' AND report IS NOT NULL AND error_code IS NULL) OR (status!='completed' AND report IS NULL)",
            name="ck_billing_collection_result",
        ),
        CheckConstraint(
            "status NOT IN ('completed','failed','ambiguous') OR attempts=1",
            name="ck_billing_collection_terminal_dispatch",
        ),
    )


class AIRequest(TenantRow, Base):
    __tablename__ = "ai_requests"
    requested_by: Mapped[str] = mapped_column(String(36))
    purpose: Mapped[str] = mapped_column(String(30))
    provider: Mapped[str] = mapped_column(String(50))
    model: Mapped[str] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(30), default="reserved")
    policy_snapshot: Mapped[dict] = mapped_column(JSON)
    context_digest: Mapped[str] = mapped_column(String(64))
    endpoint_digest: Mapped[str] = mapped_column(String(64))
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    reserved_input_units: Mapped[int]
    reserved_output_units: Mapped[int]
    reserved_cost: Mapped[Decimal | None] = mapped_column(Numeric(14, 6))
    currency: Mapped[str | None] = mapped_column(String(3))
    dispatch_token: Mapped[str | None] = mapped_column(String(36))
    dispatch_deadline: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    dispatched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    settled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    observed_input_units: Mapped[int | None]
    observed_output_units: Mapped[int | None]
    observed_cost: Mapped[Decimal | None] = mapped_column(Numeric(14, 6))
    observed_currency: Mapped[str | None] = mapped_column(String(3))
    reconciliation_digest: Mapped[str | None] = mapped_column(String(64))
    __table_args__ = (
        ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        UniqueConstraint("organization_id", "id"),
        UniqueConstraint(
            "organization_id", "id", "period_start", name="uq_ai_request_admission_period"
        ),
        Index("ix_ai_request_org_period_status", "organization_id", "period_start", "status"),
        CheckConstraint(
            "status IN ('reserved','dispatched','succeeded','ambiguous','not_dispatched','cancelled','reconciled_charge','reconciled_no_charge')",
            name="ck_ai_request_status",
        ),
        CheckConstraint(
            "reserved_input_units >= 0 AND reserved_output_units >= 0",
            name="ck_ai_request_reserve_units",
        ),
        CheckConstraint(
            "reserved_cost IS NULL OR reserved_cost >= 0", name="ck_ai_request_reserve_cost"
        ),
        CheckConstraint(
            "observed_input_units IS NULL OR observed_input_units >= 0",
            name="ck_ai_request_observed_input",
        ),
        CheckConstraint(
            "observed_output_units IS NULL OR observed_output_units >= 0",
            name="ck_ai_request_observed_output",
        ),
        CheckConstraint(
            "observed_cost IS NULL OR observed_cost >= 0", name="ck_ai_request_observed_cost"
        ),
        CheckConstraint(
            "length(context_digest)=64 AND length(endpoint_digest)=64", name="ck_ai_request_digests"
        ),
        CheckConstraint(
            "status NOT IN ('dispatched','succeeded','ambiguous','reconciled_charge','reconciled_no_charge') OR (dispatch_token IS NOT NULL AND dispatched_at IS NOT NULL)",
            name="ck_ai_request_dispatch_marker",
        ),
        CheckConstraint(
            "status NOT IN ('succeeded','reconciled_charge') OR (observed_input_units IS NOT NULL AND observed_output_units IS NOT NULL)",
            name="ck_ai_request_observed_units",
        ),
        CheckConstraint(
            "status != 'reconciled_charge' OR (observed_cost IS NOT NULL AND observed_currency IS NOT NULL)",
            name="ck_ai_request_reconciled_charge",
        ),
        CheckConstraint(
            "(reserved_cost IS NULL) = (currency IS NULL) AND (observed_cost IS NULL) = (observed_currency IS NULL)",
            name="ck_ai_request_currency_pairs",
        ),
        CheckConstraint(
            "(dispatch_token IS NULL) = (dispatched_at IS NULL)", name="ck_ai_request_dispatch_pair"
        ),
        CheckConstraint(
            "status != 'cancelled' OR dispatch_token IS NULL", name="ck_ai_request_cancelled_unsent"
        ),
        CheckConstraint(
            "((status IN ('reserved','dispatched','ambiguous')) AND settled_at IS NULL) OR ((status NOT IN ('reserved','dispatched','ambiguous')) AND settled_at IS NOT NULL)",
            name="ck_ai_request_settlement_state",
        ),
        CheckConstraint(
            "status NOT IN ('reserved','dispatched') OR (observed_input_units IS NULL AND observed_output_units IS NULL AND observed_cost IS NULL AND observed_currency IS NULL)",
            name="ck_ai_request_no_early_observation",
        ),
        CheckConstraint(
            "(status IN ('reconciled_charge','reconciled_no_charge')) = (reconciliation_digest IS NOT NULL)",
            name="ck_ai_request_reconciliation_state",
        ),
    )


class AIRequestEvent(TenantRow, Base):
    __tablename__ = "ai_request_events"
    request_id: Mapped[str] = mapped_column(String(36))
    position: Mapped[int]
    actor_id: Mapped[str] = mapped_column(String(36))
    kind: Mapped[str] = mapped_column(String(40))
    details: Mapped[dict] = mapped_column(JSON)
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "request_id"], ["ai_requests.organization_id", "ai_requests.id"]
        ),
        UniqueConstraint("organization_id", "request_id", "position"),
        CheckConstraint("position > 0", name="ck_ai_request_event_position"),
        Index("ix_ai_request_event_scope", "organization_id", "request_id"),
    )


class AIUsage(TenantRow, Base):
    __tablename__ = "ai_usage"
    request_id: Mapped[str | None] = mapped_column(String(36))
    admission_period_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    provider: Mapped[str] = mapped_column(String(50))
    purpose: Mapped[str] = mapped_column(String(30))
    input_units: Mapped[int]
    output_units: Mapped[int]
    estimated_cost: Mapped[Decimal | None] = mapped_column(Numeric(14, 6))
    model: Mapped[str | None] = mapped_column(String(100))
    billing_currency: Mapped[str | None] = mapped_column(String(3))
    pricing: Mapped[dict | None] = mapped_column(JSON)
    __table_args__ = (
        ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        ForeignKeyConstraint(
            ["organization_id", "request_id", "admission_period_start"],
            ["ai_requests.organization_id", "ai_requests.id", "ai_requests.period_start"],
            name="fk_ai_usage_request_period",
        ),
        UniqueConstraint("organization_id", "request_id", name="uq_ai_usage_request"),
        CheckConstraint(
            "(request_id IS NULL) = (admission_period_start IS NULL)",
            name="ck_ai_usage_request_period_pair",
        ),
    )


class IncidentEvent(TenantRow, Base):
    __tablename__ = "incident_events"
    incident_id: Mapped[str] = mapped_column(String(36))
    event_id: Mapped[str] = mapped_column(String(36))
    __table_args__ = (
        UniqueConstraint("organization_id", "incident_id", "event_id"),
        ForeignKeyConstraint(
            ["organization_id", "incident_id"], ["incidents.organization_id", "incidents.id"]
        ),
        ForeignKeyConstraint(
            ["organization_id", "event_id"],
            ["security_events.organization_id", "security_events.id"],
        ),
    )


class JobRole(TenantRow, Base):
    __tablename__ = "job_roles"
    title: Mapped[str] = mapped_column(String(100))
    grade: Mapped[str] = mapped_column(String(40))
    version: Mapped[int]
    currency: Mapped[str] = mapped_column(String(3))
    minimum_base: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    maximum_base: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    __table_args__ = (
        ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        UniqueConstraint("organization_id", "id"),
        UniqueConstraint("organization_id", "title", "grade", "version"),
        CheckConstraint("version > 0 AND minimum_base >= 0 AND maximum_base >= minimum_base"),
    )


class EmploymentChange(TenantRow, Base):
    __tablename__ = "employment_changes"
    employee_id: Mapped[str] = mapped_column(String(36))
    job_role_id: Mapped[str] = mapped_column(String(36))
    previous_terms_id: Mapped[str | None] = mapped_column(String(36))
    base: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    effective_on: Mapped[date] = mapped_column(Date)
    reason: Mapped[str] = mapped_column(String(1000))
    proposed_by: Mapped[str] = mapped_column(String(36))
    reviewed_by: Mapped[str | None] = mapped_column(String(36))
    status: Mapped[str] = mapped_column(default="proposed")
    resolution_reason: Mapped[str | None] = mapped_column(String(1000))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "employee_id"], ["employees.organization_id", "employees.id"]
        ),
        ForeignKeyConstraint(
            ["organization_id", "job_role_id"], ["job_roles.organization_id", "job_roles.id"]
        ),
        UniqueConstraint("organization_id", "id"),
        CheckConstraint("base >= 0"),
        CheckConstraint("status IN ('proposed','approved','rejected','applied')"),
    )


class EmploymentTerms(TenantRow, Base):
    __tablename__ = "employment_terms"
    employee_id: Mapped[str] = mapped_column(String(36))
    job_role_id: Mapped[str] = mapped_column(String(36))
    change_id: Mapped[str] = mapped_column(String(36))
    base: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    currency: Mapped[str] = mapped_column(String(3))
    effective_on: Mapped[date] = mapped_column(Date)
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "employee_id"], ["employees.organization_id", "employees.id"]
        ),
        ForeignKeyConstraint(
            ["organization_id", "job_role_id"], ["job_roles.organization_id", "job_roles.id"]
        ),
        ForeignKeyConstraint(
            ["organization_id", "change_id"],
            ["employment_changes.organization_id", "employment_changes.id"],
        ),
        UniqueConstraint("organization_id", "employee_id", "effective_on"),
        UniqueConstraint("change_id"),
        CheckConstraint("base >= 0"),
    )


class LeaveEntitlement(TenantRow, Base):
    __tablename__ = "leave_entitlements"
    employee_id: Mapped[str] = mapped_column(String(36))
    year: Mapped[int]
    allowance_days: Mapped[int]
    counting: Mapped[str] = mapped_column(String(20), default="weekdays")
    holidays: Mapped[list] = mapped_column(JSON, default=list, server_default="[]")
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "employee_id"], ["employees.organization_id", "employees.id"]
        ),
        UniqueConstraint("organization_id", "employee_id", "year"),
        CheckConstraint("year BETWEEN 2000 AND 2200 AND allowance_days BETWEEN 0 AND 366"),
        CheckConstraint("counting IN ('calendar','weekdays')"),
    )


class IncidentNote(TenantRow, Base):
    __tablename__ = "incident_notes"
    incident_id: Mapped[str] = mapped_column(String(36))
    author_id: Mapped[str] = mapped_column(String(36))
    body: Mapped[str] = mapped_column(String(4000))
    reference: Mapped[str | None] = mapped_column(String(200))
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "incident_id"], ["incidents.organization_id", "incidents.id"]
        ),
        ForeignKeyConstraint(
            ["organization_id", "author_id"], ["memberships.organization_id", "memberships.user_id"]
        ),
    )


class PayrollRule(TenantRow, Base):
    __tablename__ = "payroll_rules"
    name: Mapped[str] = mapped_column(String(100))
    version: Mapped[int]
    currency: Mapped[str] = mapped_column(String(3))
    components: Mapped[list] = mapped_column(JSON)
    __table_args__ = (
        ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        UniqueConstraint("organization_id", "name", "version"),
        UniqueConstraint("organization_id", "id"),
        CheckConstraint("version > 0"),
    )


class PayrollCalculation(TenantRow, Base):
    __tablename__ = "payroll_calculations"
    payroll_id: Mapped[str] = mapped_column(String(36), unique=True)
    rule_id: Mapped[str] = mapped_column(String(36))
    base: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    breakdown: Mapped[list] = mapped_column(JSON)
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "payroll_id"], ["payroll.organization_id", "payroll.id"]
        ),
        ForeignKeyConstraint(
            ["organization_id", "rule_id"], ["payroll_rules.organization_id", "payroll_rules.id"]
        ),
    )


class RiskPolicy(TenantRow, Base):
    __tablename__ = "risk_policies"
    version: Mapped[int]
    created_by: Mapped[str] = mapped_column(String(36))
    algorithm_version: Mapped[str] = mapped_column(String(40))
    weights: Mapped[dict] = mapped_column(JSON)
    thresholds: Mapped[dict] = mapped_column(JSON)
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "created_by"],
            ["memberships.organization_id", "memberships.user_id"],
        ),
        UniqueConstraint("organization_id", "id"),
        UniqueConstraint("organization_id", "version"),
        CheckConstraint("version > 0"),
    )


class RiskAssessment(TenantRow, Base):
    __tablename__ = "risk_assessments"
    policy_id: Mapped[str] = mapped_column(String(36))
    requested_by: Mapped[str] = mapped_column(String(36))
    request_key: Mapped[str] = mapped_column(String(100))
    request_digest: Mapped[str] = mapped_column(String(64))
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    window_end: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    synthetic: Mapped[bool]
    result: Mapped[dict] = mapped_column(JSON)
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "policy_id"], ["risk_policies.organization_id", "risk_policies.id"]
        ),
        ForeignKeyConstraint(
            ["organization_id", "requested_by"],
            ["memberships.organization_id", "memberships.user_id"],
        ),
        UniqueConstraint("organization_id", "request_key"),
        CheckConstraint("window_start <= window_end"),
        Index(
            "ix_risk_assessment_window",
            "organization_id",
            "synthetic",
            "window_end",
            "window_start",
        ),
    )
