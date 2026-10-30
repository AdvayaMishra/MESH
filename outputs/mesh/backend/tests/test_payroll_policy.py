from decimal import Decimal

from app.models import Employee, identifier
from app.payroll import Component, calculate
from conftest import DEV, HR, ORG_A, ORG_B, headers, login


def test_payroll_components_are_deterministic():
    gross, deductions, rows = calculate(
        Decimal("1000.00"),
        [
            Component(name="Allowance", kind="earning", formula="percent_of_base", value="10.00"),
            Component(name="Deduction", kind="deduction", formula="fixed", value="50.25"),
        ],
    )
    assert gross == Decimal("1100.00") and gross - deductions == Decimal("1049.75")
    assert rows[0]["amount"] == "100.00"


def test_versioned_rule_and_tenant_safe_calculation(client, db):
    employee = Employee(
        id=identifier(),
        organization_id=ORG_A,
        user_id=DEV,
        name="Fixture",
        department="Engineering",
    )
    db.add(employee)
    db.commit()
    login(HR)
    payload = {
        "name": "Local policy",
        "version": 1,
        "currency": "INR",
        "components": [
            {"name": "Allowance", "kind": "earning", "formula": "fixed", "value": "100.00"}
        ],
    }
    created = client.post("/api/v1/hr/payroll-rules", headers=headers(), json=payload)
    assert created.status_code == 201, created.text
    rule_id = created.json()["id"]
    assert (
        client.post("/api/v1/hr/payroll-rules", headers=headers(), json=payload).status_code == 409
    )
    computed = client.post(
        "/api/v1/hr/payroll/compute",
        headers=headers(),
        json={
            "employee_id": employee.id,
            "rule_id": rule_id,
            "base": "1000.00",
            "period": "2026-10",
        },
    )
    assert computed.status_code == 201, computed.text
    assert computed.json()["payroll"]["net"] == "1100.00"
    assert client.get("/api/v1/hr/payroll-rules", headers=headers(ORG_B)).json() == []


def test_mfa_enforcement_uses_verified_assurance(client, monkeypatch):
    from app.auth import Identity, identity
    from app.core.config import settings
    from app.main import app
    from conftest import OWNER

    monkeypatch.setattr(settings(), "require_privileged_mfa", True)
    assert client.get("/api/v1/organizations/current", headers=headers()).status_code == 403
    app.dependency_overrides[identity] = lambda: Identity(OWNER, f"{OWNER}@example.org", "aal2")
    assert client.get("/api/v1/organizations/current", headers=headers()).status_code == 200
