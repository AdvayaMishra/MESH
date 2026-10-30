"""Validated publication mapping shared by the synchronous route and leased worker."""

from pydantic import BaseModel, ConfigDict, Field

from app.cloud_context_schema import Snapshot
from app.models import CloudAssessment, identifier


class Report(BaseModel):
    model_config = ConfigDict(extra="forbid")
    findings: list[dict] = Field(max_length=1000)
    errors: list[dict] = Field(max_length=1000)
    partial: bool = Field(strict=True)
    coverage: list[str] = Field(max_length=20)
    limitations: list[str] = Field(min_length=1, max_length=10)
    normalized_context: Snapshot | None = None


def assessment_record(
    report: Report, organization_id: str, *, source_job_id: str | None = None
) -> CloudAssessment:
    if report.errors and not report.partial:
        raise ValueError("Unknown checks cannot produce a complete assessment")
    data = report.model_dump(exclude={"normalized_context"})
    snapshot = report.normalized_context
    assessment_id = identifier()
    context = None
    if snapshot is not None:
        if str(snapshot.envelope.organization_id) != organization_id:
            raise ValueError("Cloud context tenant mismatch")
        if snapshot.envelope.source_job_id is not None:
            raise ValueError("Only publication may bind a job")
        assessment_id = str(snapshot.envelope.assessment_id)
        context = snapshot.model_dump(mode="json", by_alias=True)
        context["envelope"]["source_job_id"] = source_job_id
        context = Snapshot.model_validate(context).model_dump(mode="json", by_alias=True)
        data["partial"] = report.partial or snapshot.envelope.partial
    return CloudAssessment(
        id=assessment_id,
        organization_id=organization_id,
        provider="aws",
        normalized_context=context,
        **data,
    )
