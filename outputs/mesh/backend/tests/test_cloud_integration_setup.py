from uuid import UUID

import boto3
import pytest
from app.auth import Principal
from app.cloud_jobs import job_status
from app.core.config import settings
from app.models import (
    AuditLog,
    BillingCollection,
    CloudAssessmentJob,
    CostRecord,
    Membership,
    identifier,
    now,
)
from conftest import ANALYST, ANALYST2, DEV, HR, ORG_A, ORG_B, OWNER, headers, login
from fastapi import HTTPException
from sqlalchemy import func, select

BASE = "/api/v1/cloud-integrations/aws"
JOBS = "/api/v1/vader/cloud/jobs"
ROLE = "arn:aws:iam::012345678901:role/synthetic-reader"


@pytest.fixture(autouse=True)
def isolated_configuration(monkeypatch):
    monkeypatch.setattr(settings(), "aws_role_bindings", {})
    monkeypatch.setattr(settings(), "aws_billing_role_bindings", {})
    monkeypatch.setattr(settings(), "environment", "development")
    monkeypatch.setattr(
        boto3, "client", lambda *a, **k: pytest.fail("Local-only setup/sample invoked AWS SDK")
    )
    monkeypatch.setattr(
        boto3,
        "Session",
        lambda *a, **k: pytest.fail("Local-only setup/sample resolved credentials"),
    )


@pytest.mark.parametrize(
    "capability,role,state,reason",
    [
        ("posture", None, "not_configured", "role_binding_missing"),
        ("billing", None, "not_configured", "role_binding_missing"),
        ("posture", ROLE, "configured_unverified", None),
        ("billing", ROLE, "configured_unverified", None),
        ("billing", "malformed", "invalid_configuration", "role_binding_invalid"),
        (
            "billing",
            ROLE.replace("arn:aws:", "arn:aws-cn:"),
            "invalid_configuration",
            "partition_unsupported",
        ),
        ("posture", ROLE.replace("arn:aws:", "arn:aws-cn:"), "configured_unverified", None),
    ],
)
def test_local_binding_status_is_tenant_scoped_and_never_claims_provider_validation(
    client, monkeypatch, capability, role, state, reason
):
    field = "aws_role_bindings" if capability == "posture" else "aws_billing_role_bindings"
    monkeypatch.setattr(settings(), field, {ORG_A: role} if role is not None else {})
    login(ANALYST if capability == "posture" else OWNER)
    response = client.get(BASE + f"/{capability}/status", headers=headers())
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["state"] == state and data["reason"] == reason
    assert data["provider_check"] == "not_performed" and not data["provider_requests_performed"]
    assert ROLE not in response.text and "012345678901" not in response.text
    assert (
        client.get(BASE + f"/{capability}/status", headers=headers(ORG_B)).json()["state"]
        == "not_configured"
    )


@pytest.mark.parametrize(
    "actor,path",
    [
        (OWNER, "/posture/status"),
        (HR, "/billing/status"),
        (ANALYST, "/billing/status"),
        (DEV, "/posture/status"),
        (ANALYST, "/billing/sample"),
        (HR, "/billing/sample"),
    ],
)
def test_setup_and_samples_preserve_distinct_finance_security_permissions(client, actor, path):
    login(actor)
    assert client.get(BASE + path, headers=headers()).status_code == 403


def test_sample_is_explicit_nonpersisting_and_currency_unit_separated(client, db):
    login(OWNER)
    url = BASE + "/billing/sample?period=2026-10"
    response = client.get(url, headers=headers())
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["synthetic"] and data["data_source"] == "sample"
    assert (
        not data["provider_verified"]
        and not data["invoice_verified"]
        and not data["affects_recorded_totals"]
    )
    assert data["batch"]["provenance"] == "fixture" and data["organization_id"] == ORG_A
    assert "provider_account_id" not in response.text and "role_arn" not in response.text
    assert {row["currency"]: row["amount"] for row in data["totals"]} == {
        "EUR": "10.00",
        "USD": "155.50",
    }
    assert {row["usage_unit"] for row in data["batch"]["observations"]} == {
        "hours",
        "gib_months",
        "requests",
    }
    assert client.get(url, headers=headers()).json()["batch"] == data["batch"]
    assert client.get(url, headers=headers(ORG_B)).json()["organization_id"] == ORG_B
    for model in (CostRecord, BillingCollection, CloudAssessmentJob):
        assert db.scalar(select(func.count()).select_from(model)) == 0
    assert (
        client.get("/api/v1/finance/cloud-billing/aws/collections", headers=headers()).json()[
            "total"
        ]
        == 0
    )
    assert db.scalar(select(AuditLog.id).where(AuditLog.action == "finance.billing.sample_read"))


@pytest.mark.parametrize("environment", ["production", "staging"])
def test_samples_disabled_outside_development(client, monkeypatch, environment):
    monkeypatch.setattr(settings(), "environment", environment)
    login(OWNER)
    assert client.get(BASE + "/billing/sample", headers=headers()).status_code == 503
    assert (
        client.get(BASE + "/billing/status", headers=headers()).json()["sample_available"] is False
    )


def test_missing_configuration_never_enqueues_or_silently_returns_sample(client, db):
    login(ANALYST)
    response = client.post(JOBS, headers=headers(), json={"request_key": "missing-role-fixture"})
    assert response.status_code == 503
    assert not db.scalars(select(CloudAssessmentJob)).all()
    login(OWNER)
    response = client.post(
        "/api/v1/finance/cloud-billing/aws/collections",
        headers=headers(),
        json={"request_key": identifier(), "period": now().strftime("%Y-%m")},
    )
    assert response.status_code == 503 and not db.scalars(select(BillingCollection)).all()


def test_cloud_job_replay_bound_to_actor_survives_binding_removal_but_new_requests_do_not(
    client, db, monkeypatch
):
    monkeypatch.setattr(settings(), "aws_role_bindings", {ORG_A: ROLE})
    login(ANALYST)
    payload = {"request_key": "actor-bound-fixture"}
    first = client.post(JOBS, headers=headers(), json=payload)
    assert first.status_code == 202, first.text
    job_id = first.json()["id"]
    login(ANALYST2)
    assert client.post(JOBS, headers=headers(), json=payload).status_code == 409
    login(ANALYST)
    monkeypatch.setattr(settings(), "aws_role_bindings", {})
    assert client.post(JOBS, headers=headers(), json=payload).json()["id"] == job_id
    assert (
        client.post(JOBS, headers=headers(), json={"request_key": "new-unconfigured"}).status_code
        == 503
    )
    assert client.post(JOBS + f"/{job_id}/cancel", headers=headers()).status_code == 200


def test_direct_cloud_job_reads_deny_a_stale_revoked_principal(db):
    row = CloudAssessmentJob(organization_id=ORG_A, requested_by=ANALYST, request_key=identifier())
    db.add(row)
    db.commit()
    db.get(Membership, (ORG_A, ANALYST)).active = False
    db.commit()
    with pytest.raises(HTTPException) as error:
        job_status(UUID(row.id), db, Principal(ANALYST, ORG_A, "security_analyst"))
    assert error.value.status_code == 403


def test_invalid_sample_period_rejected(client):
    login(OWNER)
    assert client.get(BASE + "/billing/sample?period=invalid", headers=headers()).status_code == 422
