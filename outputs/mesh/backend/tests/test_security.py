import hashlib
from datetime import timedelta
from decimal import Decimal

import pytest
from app.auth import PERMISSIONS, Identity, Principal
from app.models import (
    Employee,
    Finding,
    Incident,
    Membership,
    Project,
    Repository,
    identifier,
    now,
)
from app.security import (
    normalize_domain,
    sanitized_scanner_finding,
    validate_addresses,
    verify_webhook,
)
from app.services import accept_invitation, invitation, payroll_net
from conftest import ANALYST, DEV, HR, ORG_A, ORG_B, OWNER, headers, login
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError


@pytest.mark.parametrize("role", list(PERMISSIONS))
def test_deny_unknown_permission(role):
    with pytest.raises(HTTPException) as exc:
        Principal(OWNER, ORG_A, role).require("root")
    assert exc.value.status_code == 403


@pytest.mark.parametrize(
    "role,permission,allowed",
    [
        ("owner", "employee.read", False),
        ("owner", "payroll.write", False),
        ("hr", "response.approve", False),
        ("junior_developer", "project.approve", False),
        ("senior_developer", "invite.hr", False),
        ("security_analyst", "security.read", True),
    ],
)
def test_permission_matrix(role, permission, allowed):
    p = Principal(OWNER, ORG_A, role)
    if allowed:
        p.require(permission)
    else:
        with pytest.raises(HTTPException):
            p.require(permission)


@pytest.mark.parametrize(
    "model,route,user,fields",
    [
        (
            Employee,
            "employees",
            HR,
            {"user_id": DEV, "name": "Private", "department": "Engineering"},
        ),
        (
            Project,
            "projects",
            OWNER,
            {"name": "Private", "description": "secret", "proposer_id": DEV},
        ),
        (Repository, "repositories", ANALYST, {"full_name": "private/repo", "installation_id": 1}),
        (
            Incident,
            "vader/incidents",
            ANALYST,
            {
                "actor_id": DEV,
                "fingerprint": "abc",
                "event_ids": [],
                "risk": 20,
                "explanation": "private",
            },
        ),
    ],
)
def test_cross_tenant_object_access(client, db, model, route, user, fields):
    record = model(id=identifier(), organization_id=ORG_B, **fields)
    db.add(record)
    db.commit()
    login(user)
    response = client.get(f"/api/v1/{route}/{record.id}", headers=headers())
    assert response.status_code == 404, response.text
    assert "Private" not in response.text and "secret" not in response.text


def test_cross_tenant_finding(client, db):
    repo = Repository(
        id=identifier(), organization_id=ORG_B, full_name="private/repo", installation_id=1
    )
    db.add(repo)
    db.flush()
    finding = Finding(
        id=identifier(),
        organization_id=ORG_B,
        repository_id=repo.id,
        scanner="test",
        rule_id="x",
        severity="high",
        file_path="secret.py",
        line=1,
    )
    db.add(finding)
    db.commit()
    login(ANALYST)
    assert client.get(f"/api/v1/findings/{finding.id}", headers=headers()).status_code == 404


def test_cross_tenant_foreign_key(db):
    employee = Employee(
        id=identifier(), organization_id=ORG_A, user_id=DEV, name="A", department="A"
    )
    db.add(employee)
    db.commit()
    from app.models import Payroll

    db.add(
        Payroll(
            organization_id=ORG_B,
            employee_id=employee.id,
            period="2026-10",
            currency="INR",
            gross=100,
            deductions=0,
            net=100,
        )
    )
    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()


def test_inactive_membership_blocks_every_route(client, db):
    db.get(Membership, (ORG_A, OWNER)).active = False
    db.commit()
    assert client.get("/api/v1/organizations/current", headers=headers()).status_code == 403


def test_invitation_single_use_email_bound_and_hashed(db):
    p = Principal(OWNER, ORG_A, "owner")
    record, token = invitation(db, p, "new@example.org", "hr")
    db.flush()
    assert record.token_hash == hashlib.sha256(token.encode()).hexdigest()
    assert token != record.token_hash
    new_id = identifier()
    with pytest.raises(HTTPException) as exc:
        accept_invitation(
            db, Principal(new_id, ORG_A, ""), Identity(new_id, "wrong@example.org"), token
        )
    assert exc.value.status_code == 403
    accept_invitation(db, Principal(new_id, ORG_A, ""), Identity(new_id, "new@example.org"), token)
    db.flush()
    with pytest.raises(HTTPException):
        accept_invitation(
            db, Principal(new_id, ORG_A, ""), Identity(new_id, "new@example.org"), token
        )


def test_expired_invitation(db):
    record, token = invitation(db, Principal(OWNER, ORG_A, "owner"), "expired@example.org", "hr")
    record.expires_at = now() - timedelta(seconds=1)
    db.flush()
    uid = identifier()
    with pytest.raises(HTTPException):
        accept_invitation(db, Principal(uid, ORG_A, ""), Identity(uid, record.email), token)


def test_owner_cannot_invite_owner(db):
    with pytest.raises(HTTPException):
        invitation(db, Principal(OWNER, ORG_A, "owner"), "x@example.org", "owner")


@pytest.mark.parametrize(
    "ip",
    ["127.0.0.1", "10.0.0.1", "169.254.169.254", "::1", "::ffff:8.8.8.8", "192.168.1.1", "0.0.0.0"],
)
def test_ssrf_address_filter(ip):
    with pytest.raises(ValueError):
        validate_addresses([ip])


def test_public_address_and_domain():
    validate_addresses(["8.8.8.8", "2606:4700:4700::1111"])
    assert normalize_domain("https://Example.COM/") == "example.com"
    with pytest.raises(ValueError):
        normalize_domain("http://example.com")
    with pytest.raises(ValueError):
        normalize_domain("https://admin:secret@example.com")


def test_scanner_evidence_never_retained():
    result = sanitized_scanner_finding(
        "gitleaks", {"path": "a.py", "evidence": "sk-SECRET", "description": "sk-SECRET"}
    )
    assert "SECRET" not in str(result)
    with pytest.raises(ValueError):
        sanitized_scanner_finding("bandit", {"path": "../private"})


def test_webhook_signature():
    import hmac

    key = b"a" * 32
    signature = "sha256=" + hmac.new(key, b"body", hashlib.sha256).hexdigest()
    assert verify_webhook(b"body", signature, key)
    assert not verify_webhook(b"tampered", signature, key)


def test_payroll_exact():
    assert payroll_net(Decimal("1000.10"), Decimal("0.20")) == Decimal("999.90")
    with pytest.raises(HTTPException):
        payroll_net(Decimal("1"), Decimal("2"))


def test_invalid_payload_does_not_echo_secrets(client):
    login(HR)
    response = client.post(
        "/api/v1/hr/payroll", headers=headers(), json={"password": "VERY_SECRET"}
    )
    assert response.status_code == 422
    assert "VERY_SECRET" not in response.text


def test_unauthenticated_token_rejected(client):
    from app.auth import identity
    from app.main import app

    del app.dependency_overrides[identity]
    assert client.get("/api/v1/organizations/current", headers=headers()).status_code == 401


def test_oversized_body(client):
    assert (
        client.post("/api/v1/organizations", headers=headers(), content=b"x" * 270000).status_code
        == 413
    )


def test_client_cannot_select_unauthorized_organization(client, db):
    uid = identifier()
    db.add(Membership(organization_id=ORG_A, user_id=uid, email=f"{uid}@example.org", role="hr"))
    db.commit()
    login(uid)
    assert client.get("/api/v1/employees", headers=headers(ORG_A)).status_code == 200
    assert client.get("/api/v1/employees", headers=headers(ORG_B)).status_code == 403
