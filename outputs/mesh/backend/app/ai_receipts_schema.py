"""Provisional operator-attested reconciliation and public receipt contracts."""

from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas import Input

ReceiptState = Literal[
    "reserved",
    "dispatched",
    "succeeded",
    "ambiguous",
    "not_dispatched",
    "cancelled",
    "reconciled_charge",
    "reconciled_no_charge",
]

Counter = Annotated[int, Field(strict=True, ge=0, le=1000000)]
Amount = Annotated[
    Decimal, Field(ge=0, le=Decimal("99999999.999999"), max_digits=14, decimal_places=6)
]


class ReconciliationInput(Input):
    outcome: Literal["charge", "no_charge"]
    worker_stopped: Annotated[bool, Field(strict=True)]
    provider_billing_reviewed: Annotated[bool, Field(strict=True)]
    reference: Annotated[str, Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,99}$")]
    input_units: Counter | None = None
    output_units: Counter | None = None
    amount: Amount | None = None
    currency: Annotated[str, Field(pattern=r"^[A-Z]{3}$")] | None = None

    @model_validator(mode="after")
    def attested_outcome(self):
        if not self.worker_stopped or not self.provider_billing_reviewed:
            raise ValueError("Stopped worker and provider billing review attestations are required")
        values = (self.input_units, self.output_units, self.amount, self.currency)
        if self.outcome == "charge" and any(value is None for value in values):
            raise ValueError("A reported charge requires both counters, amount and currency")
        if self.outcome == "no_charge" and any(value is not None for value in values):
            raise ValueError("A no-charge report must not contain charge measurements")
        return self


class ReceiptOutput(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    requested_by: str
    purpose: str
    provider: str
    model: str
    status: ReceiptState
    created_at: datetime
    period_start: datetime
    reserved_input_units: int
    reserved_output_units: int
    reserved_cost: Decimal | None
    currency: str | None
    dispatch_deadline: datetime
    dispatched_at: datetime | None
    settled_at: datetime | None
    observed_input_units: int | None
    observed_output_units: int | None
    observed_cost: Decimal | None
    observed_currency: str | None
    provider_invoice_verified: Literal[False] = False
    amounts_are_provisional: Literal[True] = True


class ReceiptEventOutput(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    position: int
    actor_id: str
    kind: str
    created_at: datetime
    details: dict


class ReceiptPage(BaseModel):
    requests: list[ReceiptOutput]
    total_requests: int
    limit: int
    offset: int


class ReceiptDetail(BaseModel):
    request: ReceiptOutput
    events: list[ReceiptEventOutput]
    total_events: int
    limit: int
    offset: int
