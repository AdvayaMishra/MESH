"""Strict owner-reported reconciliation input validation."""

import pytest
from app.ai_receipts_schema import ReconciliationInput
from pydantic import ValidationError


def payload():
    return {
        "outcome": "charge",
        "worker_stopped": True,
        "provider_billing_reviewed": True,
        "reference": "operator-invoice:fixture-1",
        "input_units": 100,
        "output_units": 50,
        "amount": "0.000500",
        "currency": "USD",
    }


@pytest.mark.parametrize(
    "overrides",
    [
        {"worker_stopped": False},
        {"worker_stopped": "true"},
        {"provider_billing_reviewed": False},
        {"provider_billing_reviewed": 1},
        {"reference": ""},
        {"reference": "a" * 101},
        {"reference": "https://private.invalid/invoice"},
        {"reference": "invoice\nprivate"},
        {"input_units": True},
        {"input_units": -1},
        {"input_units": 1000001},
        {"output_units": 1.5},
        {"input_units": None},
        {"output_units": None},
        {"amount": None},
        {"currency": None},
        {"amount": "NaN"},
        {"amount": "Infinity"},
        {"amount": "-0.1"},
        {"amount": "100000000"},
        {"amount": "0.0000001"},
        {"currency": "usd"},
        {"currency": "USDD"},
        {"outcome": "verified_provider_invoice"},
        {"private_comment": "not accepted"},
    ],
)
def test_invalid_or_unattested_candidate_reconciliation_is_rejected(overrides):
    with pytest.raises(ValidationError):
        ReconciliationInput.model_validate(payload() | overrides)


def test_zero_charge_is_explicit_and_counters_are_not_boolean():
    result = ReconciliationInput.model_validate(
        payload() | {"amount": "0", "input_units": 0, "output_units": 0}
    )
    assert result.amount == 0 and result.input_units == 0


def test_no_charge_omits_measurements_instead_of_inventing_zero_usage():
    data = {
        key: value
        for key, value in payload().items()
        if key not in {"input_units", "output_units", "amount", "currency"}
    }
    result = ReconciliationInput.model_validate(data | {"outcome": "no_charge"})
    assert result.input_units is None and result.amount is None
    with pytest.raises(ValidationError):
        ReconciliationInput.model_validate(data | {"outcome": "no_charge", "input_units": 0})
