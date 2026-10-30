from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, field_validator

from app.telemetry_schema import EventCategory, EventContext

Name = Annotated[str, Field(min_length=1, max_length=200)]
Money = Annotated[Decimal, Field(ge=0, max_digits=14, decimal_places=2)]
Role = Literal["owner", "hr", "senior_developer", "junior_developer", "security_analyst"]


def real_month(value: str) -> str:
    date.fromisoformat(value + "-01")
    return value


Month = Annotated[str, Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$"), AfterValidator(real_month)]


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class OrganizationInput(Input):
    name: Name


class DomainInput(Input):
    website: Annotated[str, Field(min_length=1, max_length=2048)]

    @field_validator("website")
    @classmethod
    def domain(cls, value: str) -> str:
        from app.security import normalize_domain

        return normalize_domain(value)


class OrganizationOutput(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    name: str
    status: str
    verification_status: str


class InviteInput(Input):
    email: Annotated[
        str, Field(min_length=3, max_length=254, pattern=r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
    ]
    role: Role

    @field_validator("email")
    @classmethod
    def normalize(cls, value: str) -> str:
        return value.lower()


class InviteOutput(BaseModel):
    id: str
    email: str
    role: str
    status: str
    expires_at: datetime


class InviteDeliveryOutput(BaseModel):
    invitation_id: str
    job_id: str | None = None
    state: Literal[
        "not_queued",
        "queued",
        "retrying",
        "failed",
        "smtp_accepted",
        "skipped",
        "processed_unknown",
    ]
    attempts: int = 0
    queued_at: datetime | None = None
    next_attempt_at: datetime | None = None
    processed_at: datetime | None = None
    outcome: (
        Literal["smtp_accepted", "skipped_inactive", "skipped_expired", "skipped_superseded"] | None
    ) = None
    inbox_delivery_verified: Literal[False] = False


class InviteAccept(Input):
    token: Annotated[str, Field(min_length=40, max_length=200)]


class EmployeeInput(Input):
    user_id: UUID
    name: Name
    department: Annotated[str, Field(min_length=1, max_length=100)]


class EmployeeOutput(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    user_id: str
    name: str
    department: str
    status: str
    verification_status: str
    email: str | None = None
    app_role: Role | None = None
    created_at: datetime | None = None


class UserProfileOutput(BaseModel):
    user_id: UUID
    organization_id: UUID
    role: Role
    email: str
    employee_id: UUID | None
    name: str | None
    owner_name: str | None


class PayrollInput(Input):
    employee_id: UUID
    period: Month
    currency: Annotated[str, Field(pattern=r"^[A-Z]{3}$")]
    gross: Money
    deductions: Money


class PayrollOutput(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    employee_id: str
    period: str
    currency: str
    gross: Decimal
    deductions: Decimal
    net: Decimal


class ProjectInput(Input):
    name: Name
    description: Annotated[str, Field(max_length=4000)] = ""


class ProjectOutput(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    name: str
    description: str
    proposer_id: str
    status: str


class ProjectDecision(Input):
    decision: Literal["reviewed", "approved", "rejected"]


class TaskInput(Input):
    project_id: UUID
    assignee_id: UUID
    title: Name


class TaskOutput(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    project_id: str
    assignee_id: str
    title: str
    status: str


class EventInput(Input):
    context: EventContext = Field(default_factory=EventContext)
    session_id: Annotated[str | None, Field(max_length=100)] = None
    resource_id: Annotated[str | None, Field(max_length=100)] = None
    source_id: Annotated[str, Field(min_length=1, max_length=150)]
    occurred_at: datetime
    actor_id: Annotated[str, Field(min_length=1, max_length=100)]
    category: EventCategory
    action: Annotated[str, Field(min_length=1, max_length=80)]
    result: Literal["success", "failure"]
    count: Annotated[int, Field(ge=1, le=1000000)] = 1

    @field_validator("occurred_at")
    @classmethod
    def aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("Timestamp must include timezone")
        return value


CorrelationState = Literal[
    "matched", "insufficient", "disabled", "excluded", "incomplete", "not_recomputed"
]


class EventOutput(BaseModel):
    event_id: str
    duplicate: bool
    incident_id: str | None
    correlation_status: CorrelationState = "not_recomputed"


class SecurityEventOutput(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    source_id: str
    occurred_at: datetime
    actor_id: str
    category: str
    action: str
    result: str
    count: int
    synthetic: bool
    session_id: str | None
    resource_id: str | None
    context: EventContext
    context_provenance: Literal["reported_unverified"] = "reported_unverified"


class FindingDependency(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    ecosystem: Literal["PyPI", "npm"]
    version: str


class FindingOutput(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    repository_id: str
    scanner: str
    rule_id: str
    file_path: str
    line: int
    severity: str
    status: str
    column: int | None = None
    dependency: FindingDependency | None = None
    scan_job_id: str | None = None
    commit_sha: str | None = None
    identity_id: str | None = None


class AnomalyOutput(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    event_id: str
    rule: str
    weight: int
    explanation: str


class IncidentOutput(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    actor_id: str
    event_ids: list[str]
    risk: int
    explanation: str
    status: str
    synthetic: bool
    correlation_policy_id: str | None = None
    correlation_snapshot: dict | None = None


class ResponseInput(Input):
    incident_id: UUID
    action: Literal["recommend_mfa", "revoke_session", "restrict_account", "reduce_permissions"]


class ResponseOutput(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    incident_id: str
    action: str
    status: str
    mode: str
    approved_by: str | None


class TrustInput(Input):
    user_id: UUID
    reference: Annotated[str, Field(min_length=1, max_length=100)]
    delta: Annotated[int, Field(ge=-10, le=10)]
    reason: Annotated[str, Field(min_length=10, max_length=500)]


class SummaryOutput(BaseModel):
    provider: Literal["local-deterministic"] = "local-deterministic"
    incident_id: str
    summary: str
    limitations: list[str]
