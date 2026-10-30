from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.finding_states import FindingState
from app.schemas import Input, Money, Month, Name


class Row(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str


class JobMetadata(Row):
    topic: str
    status: Literal["pending", "delivered", "dead_letter"]
    attempts: int
    created_at: datetime
    available_at: datetime


class DepartmentInput(Input):
    name: Annotated[str, Field(min_length=1, max_length=100)]


class DepartmentOutput(Row):
    name: str


class LeaveInput(Input):
    employee_id: UUID
    starts_on: date
    ends_on: date
    reason: Annotated[str, Field(min_length=1, max_length=1000)]

    @model_validator(mode="after")
    def dates(self):
        if self.ends_on < self.starts_on or (self.ends_on - self.starts_on).days > 366:
            raise ValueError("Invalid leave interval")
        return self


class LeaveOutput(Row):
    employee_id: str
    starts_on: date
    ends_on: date
    status: str
    reason: str


class Decision(Input):
    decision: Literal["approved", "rejected"]


class ComplaintInput(Input):
    subject: Name
    body: Annotated[str, Field(min_length=1, max_length=4000)]


class ComplaintOutput(Row):
    author_id: str
    subject: str
    body: str
    status: str


class LifecycleInput(Input):
    employee_id: UUID
    kind: Literal["onboarding", "promotion", "role_change", "transfer", "offboarding", "rehire"]
    role: Literal["senior_developer", "junior_developer", "security_analyst"] | None = None
    department: Annotated[str | None, Field(min_length=1, max_length=100)] = None
    provision_scim: bool = False


class LifecycleOutput(Row):
    employee_id: str
    kind: str
    snapshot: dict
    proposed: dict
    status: str
    history: list


class CostInput(Input):
    request_key: UUID
    period: Month
    department: Annotated[str, Field(min_length=1, max_length=100)]
    category: Literal["cloud", "personnel", "infrastructure", "other"]
    currency: Annotated[str, Field(pattern=r"^[A-Z]{3}$")]
    amount: Money
    billing_provider: Literal["aws", "azure", "gcp"] | None = None
    usage_quantity: Annotated[Decimal | None, Field(ge=0, max_digits=20, decimal_places=6)] = None
    usage_unit: Literal["hours", "gib_hours", "gib_months", "requests", "units"] | None = None

    @model_validator(mode="after")
    def usage_pair(self):
        if (self.usage_quantity is None) != (self.usage_unit is None):
            raise ValueError("Usage quantity and unit must be supplied together")
        if self.usage_quantity is not None and self.category not in {"cloud", "infrastructure"}:
            raise ValueError("Infrastructure usage requires a cloud or infrastructure cost")
        return self


class CostOutput(Row):
    period: str
    department: str
    category: str
    currency: str
    amount: Decimal
    source: str
    request_key: str | None
    recorded_by: str | None
    billing_provider: str | None
    usage_quantity: Decimal | None
    usage_unit: str | None


class BudgetInput(Input):
    period: Month
    currency: Annotated[str, Field(pattern=r"^[A-Z]{3}$")]
    amount: Money


class BudgetOutput(Row):
    period: str
    currency: str
    amount: Decimal


class BudgetVarianceOutput(BaseModel):
    period: str
    currency: str
    budget: Decimal | None
    actual: Decimal
    variance: Decimal | None
    variance_percent: Decimal | None
    over_budget: bool | None
    provenance: Literal["recorded_costs_only"] = "recorded_costs_only"


class InfrastructureUsageOutput(BaseModel):
    period: str
    currency: str
    billing_provider: str | None
    usage_unit: str
    quantity: Decimal
    recorded_cost: Decimal
    provenance: Literal["reported_records_only"] = "reported_records_only"


class FinanceSummary(BaseModel):
    currency: str
    total: Decimal
    months: dict[str, Decimal]
    departments: dict[str, Decimal]
    forecast_next_month: Decimal | None
    forecast_method: str
    provenance: Literal["recorded_costs_only"] = "recorded_costs_only"


class MemberInput(Input):
    user_id: UUID
    manager: bool = False


class MemberOutput(Row):
    project_id: str
    user_id: str
    manager: bool


class SprintInput(Input):
    name: Annotated[str, Field(min_length=1, max_length=100)]
    starts_on: date
    ends_on: date

    @model_validator(mode="after")
    def dates(self):
        if self.ends_on < self.starts_on:
            raise ValueError("Invalid sprint interval")
        return self


class SprintOutput(Row):
    project_id: str
    name: str
    starts_on: date
    ends_on: date
    status: str


class CommentInput(Input):
    body: Annotated[str, Field(min_length=1, max_length=4000)]


class CommentOutput(Row):
    project_id: str
    author_id: str
    body: str


class TaskUpdate(Input):
    status: Literal["todo", "in_progress", "review", "done"]
    priority: Literal["low", "normal", "high", "critical"] | None = None
    deadline: datetime | None = None
    sprint_id: UUID | None = None


class RepositoryInput(Input):
    full_name: Annotated[str, Field(pattern=r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$", max_length=200)]
    installation_id: Annotated[int, Field(gt=0)]
    project_id: UUID


class RepositoryOutput(Row):
    full_name: str
    installation_id: int
    enabled: bool


class ScanInput(Input):
    repository_id: UUID
    commit_sha: Annotated[str, Field(pattern=r"^[a-f0-9]{40}$")]
    request_key: Annotated[str, Field(min_length=8, max_length=100)]


class ScanOutput(Row):
    repository_id: str
    commit_sha: str
    status: str
    attempts: int
    report: dict = Field(
        description="Operational scan snapshot. stage and progress (0-100) describe phase completion, not elapsed time; completed_steps records finished phases. Progress reaches 100 only with durable completed status. Error text is sanitized; no credentials or source content are returned."
    )


class FindingDecision(Input):
    status: FindingState


class FindingTransitionOutput(BaseModel):
    id: str
    actor_id: str
    from_status: FindingState
    to_status: FindingState
    at: datetime


class FindingHistoryOutput(BaseModel):
    changes: list[FindingTransitionOutput]
    limit: int
    offset: int
    provenance: str
    resolution: str


class RemediationGroup(BaseModel):
    scanner: str
    rule_id: str
    severity: str
    open: int
    triaged: int
    investigating: int
    confirmed: int
    accepted_risk: int
    resolved: int
    false_positive: int
    total: int
    first_observed_at: datetime
    last_observed_at: datetime


class RemediationOutput(BaseModel):
    groups: list[RemediationGroup]
    total_groups: int
    limit: int
    offset: int
    counting: Literal["finding_observations"] = "finding_observations"


class DocumentOutput(Row):
    employee_id: str
    media_type: str
    status: str
    expires_at: datetime
    ocr_status: str


class DocumentQueueItem(DocumentOutput):
    created_at: datetime
    active_hold: bool
    expired: bool


class DocumentQueue(BaseModel):
    items: list[DocumentQueueItem]
    limit: int
    offset: int
    has_more: bool


class SignedDocument(BaseModel):
    url: str
    expires_in: int = 60
