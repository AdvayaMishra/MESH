"""Future billing adapter boundary. Fixtures never impersonate live cloud billing."""

from decimal import Decimal
from typing import Annotated, Literal, Protocol

from fastapi import HTTPException
from pydantic import Field, TypeAdapter, model_validator

from app.aws_billing import AWSBillingReport
from app.schemas import Input, Money, Month

BillingProvider = Literal["aws", "azure", "gcp"]
UsageUnit = Literal["hours", "gib_hours", "gib_months", "requests", "units"]


class BillingObservation(Input):
    source_reference: Annotated[str, Field(min_length=1, max_length=150)]
    period: Month
    department: Annotated[str, Field(min_length=1, max_length=100)]
    currency: Annotated[str, Field(pattern=r"^[A-Z]{3}$")]
    amount: Money
    usage_quantity: Annotated[Decimal | None, Field(ge=0, max_digits=20, decimal_places=6)] = None
    usage_unit: UsageUnit | None = None

    @model_validator(mode="after")
    def usage(self):
        if (self.usage_quantity is None) != (self.usage_unit is None):
            raise ValueError("Billing usage quantity and unit must be paired")
        return self


class BillingBatch(Input):
    provider: BillingProvider
    period: Month
    provenance: Literal["fixture", "authorized_provider"]
    observations: Annotated[list[BillingObservation], Field(max_length=1000)]


class BillingAdapter(Protocol):
    def collect(self, period: str) -> BillingBatch | AWSBillingReport: ...


class FixtureBillingAdapter:
    def __init__(self, provider: BillingProvider, rows: list[BillingObservation]):
        if provider not in {"aws", "azure", "gcp"} or len(rows) > 1000:
            raise ValueError("Invalid bounded billing fixture")
        references = [(row.period, row.source_reference) for row in rows]
        if len(references) != len(set(references)):
            raise ValueError("Fixture references must be unique within each period")
        self.provider, self.rows = provider, rows

    def collect(self, period: str) -> BillingBatch:
        selected = TypeAdapter(Month).validate_python(period)
        return BillingBatch(
            provider=self.provider,
            period=selected,
            provenance="fixture",
            observations=[row.model_copy(deep=True) for row in self.rows if row.period == selected],
        )


def live_billing_adapter(
    provider: BillingProvider, *, organization_id: str | None = None
) -> BillingAdapter:
    if provider not in {"aws", "azure", "gcp"}:
        raise HTTPException(422, "Unsupported billing provider")
    if provider == "aws" and organization_id is not None:
        from app.aws_billing import configured_billing

        return configured_billing(organization_id)
    raise HTTPException(
        503, "Live billing requires an authorized account binding and implemented provider adapter"
    )
