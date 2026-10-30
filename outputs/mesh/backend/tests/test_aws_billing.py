from copy import deepcopy
from datetime import UTC, date, datetime
from decimal import Decimal
from types import SimpleNamespace

import boto3
import pytest
from app import aws_billing
from app.aws_billing import AWSBillingAdapter, configured_billing, period_bounds
from app.cloud_identity import AWSAccountIdentity
from conftest import ORG_A
from fastapi import HTTPException
from test_cloud_identity import ASSUMED, CALLER, ROLE

IDENTITY = AWSAccountIdentity.from_role(ROLE)
TODAY = datetime(2026, 10, 26, tzinfo=UTC)


def response(service="Amazon S3", amount="12.345678", currency="USD", **kwargs):
    return {
        "ResultsByTime": [
            {
                "TimePeriod": {"Start": "2026-09-01", "End": "2026-10-01"},
                "Estimated": False,
                "Groups": [
                    {
                        "Keys": [service],
                        "Metrics": {"UnblendedCost": {"Amount": amount, "Unit": currency}},
                    }
                ],
            }
        ],
        **kwargs,
    }


class CE:
    def __init__(self, pages):
        self.pages, self.calls = pages, []

    def get_cost_and_usage(self, **kwargs):
        self.calls.append(kwargs)
        return deepcopy(self.pages[len(self.calls) - 1])


@pytest.fixture(autouse=True)
def fixed_clock(monkeypatch):
    monkeypatch.setattr(aws_billing, "now", lambda: TODAY)


def test_billing_is_exact_account_filtered_and_keeps_refunds_and_currencies_separate():
    client = CE(
        [
            response(NextPageToken="next"),
            response("Refund", "-1.23", NextPageToken="last"),
            response("Other", "2.00", "EUR"),
        ]
    )
    report = AWSBillingAdapter(ORG_A, IDENTITY, client).collect("2026-09")
    assert {item.currency: item.amount for item in report.totals} == {
        "USD": Decimal("11.115678"),
        "EUR": Decimal("2.00"),
    }
    assert report.provenance == "authorized_provider" and report.invoice_verified is False
    assert len(report.observations) == 3
    for call in client.calls:
        assert call["Filter"]["Dimensions"] == {
            "Key": "LINKED_ACCOUNT",
            "Values": ["012345678901"],
            "MatchOptions": ["EQUALS"],
        }
        assert call["GroupBy"] == [{"Type": "DIMENSION", "Key": "SERVICE"}]
        assert call["Metrics"] == ["UnblendedCost"] and "UsageQuantity" not in str(call)
    assert client.calls[1]["NextPageToken"] == "next"


@pytest.mark.parametrize("amount", ["NaN", "Infinity", "1e10", "1.12345678901", "9" * 15, 12.0])
def test_invalid_or_inexact_provider_amount_is_unavailable(amount):
    with pytest.raises(HTTPException) as error:
        AWSBillingAdapter(ORG_A, IDENTITY, CE([response(amount=amount)])).collect("2026-09")
    assert error.value.status_code == 503


def test_wrong_period_and_repeated_tokens_never_return_partial_success():
    invalid = response()
    invalid["ResultsByTime"][0]["TimePeriod"]["Start"] = "2026-08-01"
    for pages in (
        [invalid],
        [response(NextPageToken="same"), response("Other", NextPageToken="same")],
        [response(NextPageToken="next"), response()],
    ):
        with pytest.raises(HTTPException) as error:
            AWSBillingAdapter(ORG_A, IDENTITY, CE(pages)).collect("2026-09")
        assert error.value.status_code == 503


def test_estimated_costs_remain_estimated():
    page = response()
    page["ResultsByTime"][0]["Estimated"] = True
    assert AWSBillingAdapter(ORG_A, IDENTITY, CE([page])).collect("2026-09").estimated


@pytest.mark.parametrize("period", ["2026-11", "2025-10", "2026-13", "garbage"])
def test_invalid_period_makes_no_provider_call(period):
    client = CE([])
    with pytest.raises(HTTPException) as error:
        AWSBillingAdapter(ORG_A, IDENTITY, client).collect(period)
    assert error.value.status_code == 422 and not client.calls


def test_calendar_year_boundary_and_leap_february():
    assert period_bounds("2025-12", date(2026, 1, 1))[2] == date(2026, 1, 1)
    assert period_bounds("2024-02", date(2024, 2, 29))[2] == date(2024, 3, 1)


def test_no_billing_binding_does_not_reuse_posture_access(monkeypatch):
    monkeypatch.setattr(
        aws_billing,
        "settings",
        lambda: SimpleNamespace(aws_role_bindings={ORG_A: ROLE}, aws_billing_role_bindings={}),
    )
    monkeypatch.setattr(
        boto3, "client", lambda *args, **kwargs: pytest.fail("Unbound billing contacted AWS")
    )
    with pytest.raises(HTTPException) as error:
        configured_billing(ORG_A)
    assert error.value.status_code == 503


def test_billing_session_verifies_account_before_constructing_ce_client(monkeypatch):
    calls = []
    caller = deepcopy(CALLER)

    class STS:
        def assume_role(self, **kwargs):
            assert "ce:GetCostAndUsage" in kwargs["Policy"]
            assert kwargs["ExternalId"] == ORG_A
            assert "iam:" not in kwargs["Policy"]
            return {
                "Credentials": {
                    "AccessKeyId": "fixture",
                    "SecretAccessKey": "fixture",
                    "SessionToken": "fixture",
                },
                "AssumedRoleUser": ASSUMED,
            }

        def get_caller_identity(self):
            return caller

    class Session:
        def __init__(self, **kwargs):
            pass

        def client(self, name, **kwargs):
            assert kwargs["config"].retries["total_max_attempts"] == 1
            calls.append(name)
            return STS() if name == "sts" else CE([response()])

    monkeypatch.setattr(
        aws_billing, "settings", lambda: SimpleNamespace(aws_billing_role_bindings={ORG_A: ROLE})
    )
    monkeypatch.setattr(boto3, "client", lambda *args, **kwargs: STS())
    monkeypatch.setattr(boto3, "Session", Session)
    assert configured_billing(ORG_A).collect("2026-09").provider_account_id == "012345678901"
    assert calls == ["sts", "ce"]
    calls.clear()
    caller["Account"] = "999999999999"
    with pytest.raises(HTTPException):
        configured_billing(ORG_A)
    assert calls == ["sts"]


def test_provider_error_is_sanitized():
    client = CE([])

    def fail(**kwargs):
        raise RuntimeError("DO_NOT_EXPOSE")

    client.get_cost_and_usage = fail
    with pytest.raises(HTTPException) as error:
        AWSBillingAdapter(ORG_A, IDENTITY, client).collect("2026-09")
    assert "DO_NOT_EXPOSE" not in error.value.detail
