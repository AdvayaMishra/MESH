"""Account-filtered Cost Explorer adapter. Reports are observations, not invoices."""

import json
import re
import time
from datetime import date
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from fastapi import HTTPException
from pydantic import AwareDatetime, Field, StrictBool, TypeAdapter, model_validator

from app.cloud_identity import AWSAccountIdentity
from app.core.config import settings
from app.models import now
from app.schemas import Input, Month

SignedCost = Annotated[Decimal, Field(max_digits=24, decimal_places=10, allow_inf_nan=False)]


class ServiceCost(Input):
    service: Annotated[str, Field(min_length=1, max_length=128, pattern=r"^[^\x00-\x1f]+$")]
    amount: SignedCost
    currency: Annotated[str, Field(pattern=r"^[A-Z]{3}$")]


class CurrencyCost(Input):
    currency: Annotated[str, Field(pattern=r"^[A-Z]{3}$")]
    amount: SignedCost


class AWSBillingReport(Input):
    provider: Literal["aws"] = "aws"
    organization_id: UUID
    provider_account_id: Annotated[str, Field(pattern=r"^[0-9]{12}$")]
    partition: Literal["aws"] = "aws"
    provenance: Literal["authorized_provider", "synthetic_fixture"] = "authorized_provider"
    synthetic: StrictBool = False
    period: Month
    period_start: date
    period_end: date
    metric: Literal["UnblendedCost"] = "UnblendedCost"
    estimated: StrictBool
    collected_at: AwareDatetime
    observations: Annotated[list[ServiceCost], Field(max_length=1000)]
    totals: Annotated[list[CurrencyCost], Field(max_length=20)]
    invoice_verified: Literal[False] = False
    limitations: Annotated[
        list[Annotated[str, Field(max_length=256)]], Field(min_length=1, max_length=10)
    ]

    @model_validator(mode="after")
    def coherent_report(self):
        if self.synthetic != (self.provenance == "synthetic_fixture"):
            raise ValueError("Billing provenance mismatch")
        start = date.fromisoformat(self.period + "-01")
        end = date(start.year + (start.month == 12), 1 if start.month == 12 else start.month + 1, 1)
        if (self.period_start, self.period_end) != (start, end):
            raise ValueError("Billing report period mismatch")
        keys = [(item.service, item.currency) for item in self.observations]
        if len(keys) != len(set(keys)):
            raise ValueError("Duplicate billing observation")
        expected: dict[str, Decimal] = {}
        for item in self.observations:
            expected[item.currency] = expected.get(item.currency, Decimal(0)) + item.amount
        actual = {item.currency: item.amount for item in self.totals}
        if len(actual) != len(self.totals) or actual != expected:
            raise ValueError("Billing totals must exactly match retained observations")
        if len(self.model_dump_json().encode()) > 512 * 1024:
            raise ValueError("Billing report exceeds byte bound")
        return self


def period_bounds(period: str, today: date) -> tuple[str, date, date]:
    selected = TypeAdapter(Month).validate_python(period)
    start = date.fromisoformat(selected + "-01")
    months = (today.year - start.year) * 12 + today.month - start.month
    if not 0 <= months <= 11:
        raise ValueError("Billing period must be within the current twelve calendar months")
    end = date(start.year + (start.month == 12), 1 if start.month == 12 else start.month + 1, 1)
    return selected, start, end


class AWSBillingAdapter:
    def __init__(self, organization_id: str, identity: AWSAccountIdentity, client):
        self.organization_id = UUID(organization_id)
        if identity.partition != "aws":
            raise ValueError("Billing partition is not supported")
        self.identity, self.client = identity, client

    def collect(self, period: str) -> AWSBillingReport:
        try:
            selected, start, end = period_bounds(period, now().date())
        except ValueError:
            raise HTTPException(
                422, "Billing period must be within the current twelve calendar months"
            ) from None
        try:
            token = None
            tokens = set()
            rows: dict[tuple[str, str], ServiceCost] = {}
            deadline = time.monotonic() + 60
            estimated = False
            for _ in range(10):
                if time.monotonic() > deadline:
                    raise ValueError("Billing soft time budget exceeded")
                response = self.client.get_cost_and_usage(
                    TimePeriod={"Start": start.isoformat(), "End": end.isoformat()},
                    Granularity="MONTHLY",
                    Metrics=["UnblendedCost"],
                    GroupBy=[{"Type": "DIMENSION", "Key": "SERVICE"}],
                    Filter={
                        "Dimensions": {
                            "Key": "LINKED_ACCOUNT",
                            "Values": [self.identity.account_id],
                            "MatchOptions": ["EQUALS"],
                        }
                    },
                    **({"NextPageToken": token} if token else {}),
                )
                if (
                    time.monotonic() >= deadline
                    or len(json.dumps(response, default=str).encode()) > 2 * 1024 * 1024
                ):
                    raise ValueError("Billing response exceeds byte bound")
                periods = response["ResultsByTime"]
                if not isinstance(periods, list) or len(periods) != 1:
                    raise ValueError("Unexpected billing time windows")
                result = periods[0]
                if (
                    result["TimePeriod"] != {"Start": start.isoformat(), "End": end.isoformat()}
                    or type(result["Estimated"]) is not bool
                ):
                    raise ValueError("Billing response period is inconsistent")
                estimated = estimated or result["Estimated"]
                groups = result["Groups"]
                if not isinstance(groups, list) or len(groups) > 1000:
                    raise ValueError("Billing group bound exceeded")
                for group in groups:
                    if time.monotonic() >= deadline:
                        raise ValueError("Billing processing exceeded time bound")
                    keys = group["Keys"]
                    if not isinstance(keys, list) or len(keys) != 1:
                        raise ValueError("Unexpected billing grouping")
                    metric = group["Metrics"]["UnblendedCost"]
                    amount = metric["Amount"]
                    if not isinstance(amount, str) or not re.fullmatch(
                        r"-?[0-9]{1,14}(?:\.[0-9]{1,10})?", amount
                    ):
                        raise ValueError("Invalid exact billing amount")
                    row = ServiceCost(
                        service=keys[0], amount=Decimal(amount), currency=metric["Unit"]
                    )
                    key = (row.service, row.currency)
                    if key in rows or len(rows) >= 1000:
                        raise ValueError("Duplicate or excessive billing groups")
                    rows[key] = row
                token = response.get("NextPageToken")
                if token is None:
                    break
                if not isinstance(token, str) or not token or len(token) > 8192 or token in tokens:
                    raise ValueError("Invalid billing continuation")
                tokens.add(token)
            else:
                raise ValueError("Billing page bound exceeded")
            totals: dict[str, Decimal] = {}
            if time.monotonic() >= deadline:
                raise ValueError("Billing processing exceeded time bound")
            for row in rows.values():
                totals[row.currency] = totals.get(row.currency, Decimal(0)) + row.amount
            report = AWSBillingReport(
                organization_id=self.organization_id,
                provider_account_id=self.identity.account_id,
                period=selected,
                period_start=start,
                period_end=end,
                estimated=estimated,
                collected_at=now(),
                observations=sorted(rows.values(), key=lambda row: (row.currency, row.service)),
                totals=[
                    CurrencyCost(currency=currency, amount=amount)
                    for currency, amount in sorted(totals.items())
                ],
                limitations=[
                    "Account-filtered monthly UnblendedCost observations; current or adjusted periods can change.",
                    "Credits and refunds may be negative. Currencies are kept separate; usage units are not aggregated.",
                    "Not a verified invoice and not automatically posted into manual finance records.",
                ],
            )
            if len(report.model_dump_json().encode()) > 512 * 1024:
                raise ValueError("Billing report exceeds byte bound")
            if time.monotonic() >= deadline:
                raise ValueError("Billing publication exceeded time bound")
            return report
        except Exception:
            raise HTTPException(
                503, "AWS billing observation is unavailable or incomplete"
            ) from None


def configured_billing(organization_id: str) -> AWSBillingAdapter:
    role = settings().aws_billing_role_bindings.get(organization_id)
    if not role:
        raise HTTPException(503, "A separate authorized AWS billing role binding is required")
    try:
        import boto3
        from botocore.config import Config

        identity = AWSAccountIdentity.from_role(role)
        external_id = str(UUID(organization_id))
        if identity.partition != "aws":
            raise ValueError("Unsupported billing partition")
        config = Config(connect_timeout=5, read_timeout=10, retries={"total_max_attempts": 1})
        response = boto3.client("sts", config=config).assume_role(
            RoleArn=role,
            RoleSessionName="mesh-billing",
            DurationSeconds=900,
            ExternalId=external_id,
            Policy=json.dumps(
                {
                    "Version": "2012-10-17",
                    "Statement": [
                        {"Effect": "Allow", "Action": ["ce:GetCostAndUsage"], "Resource": "*"}
                    ],
                }
            ),
        )
        credentials = response["Credentials"]
        session = boto3.Session(
            aws_access_key_id=credentials["AccessKeyId"],
            aws_secret_access_key=credentials["SecretAccessKey"],
            aws_session_token=credentials["SessionToken"],
        )
        identity.verify_session(
            response["AssumedRoleUser"], session.client("sts", config=config).get_caller_identity()
        )
        return AWSBillingAdapter(
            organization_id, identity, session.client("ce", region_name="us-east-1", config=config)
        )
    except Exception:
        raise HTTPException(503, "Authorized AWS billing session is unavailable") from None
