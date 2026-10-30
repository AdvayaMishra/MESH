import pytest
from app.auth import Principal
from app.core.config import settings
from app.telemetry_retention import retire
from conftest import ORG_A
from fastapi import HTTPException


def test_telemetry_retirement_is_disabled_without_an_operator_policy(db, monkeypatch):
    monkeypatch.setattr(settings(), "telemetry_retention_days", {})
    with pytest.raises(HTTPException) as exc:
        retire(db, Principal("retention-worker", ORG_A, "system"))
    assert exc.value.status_code == 503


def test_telemetry_retirement_does_not_fake_postgres_enforcement_in_sqlite(db, monkeypatch):
    monkeypatch.setattr(settings(), "telemetry_retention_days", {ORG_A: 90})
    with pytest.raises(HTTPException) as exc:
        retire(db, Principal("retention-worker", ORG_A, "system"))
    assert exc.value.status_code == 503


def test_telemetry_retirement_enforces_bounded_batch_size(db, monkeypatch):
    monkeypatch.setattr(settings(), "telemetry_retention_days", {ORG_A: 90})
    with pytest.raises(HTTPException) as exc:
        retire(db, Principal("retention-worker", ORG_A, "system"), batch_size=1001)
    assert exc.value.status_code == 422
