"""Backend journey with explicit identity, email, malware and Storage test doubles."""

import io

from app.core.config import settings
from app.models import identifier
from app.worker import consume
from conftest import ANALYST, DEV, HR, OWNER, headers, login
from cryptography.fernet import Fernet
from PIL import Image
from pydantic import SecretStr


def test_owner_hr_employee_project_and_security_journey(client, db, monkeypatch):
    monkeypatch.setattr(settings(), "smtp_host", "fixture")
    monkeypatch.setattr(
        settings(), "mail_encryption_key", SecretStr(Fernet.generate_key().decode())
    )
    delivered = {}
    monkeypatch.setattr(
        "app.worker.send_invitation", lambda email, token, org: delivered.update({email: token})
    )
    monkeypatch.setattr("app.documents.malware_gate", lambda _: None)
    monkeypatch.setattr("app.documents.PrivateStorage.upload", lambda *a: None)
    response = client.post("/api/v1/organizations", json={"name": "Journey fixture"})
    assert response.status_code == 201, response.text
    organization = response.json()["id"]
    selected = headers(organization)

    def invite(issuer, user, role):
        login(issuer)
        email = f"{user}@example.org"
        result = client.post(
            "/api/v1/invitations", headers=selected, json={"email": email, "role": role}
        )
        assert result.status_code == 201, result.text
        consume(db, organization)
        db.commit()
        login(user)
        accepted = client.post(
            "/api/v1/invitations/accept", headers=selected, json={"token": delivered[email]}
        )
        assert accepted.status_code == 200, accepted.text
        assert accepted.json()["role"] == role

    invite(OWNER, HR, "hr")
    invite(HR, DEV, "junior_developer")
    invite(HR, ANALYST, "security_analyst")
    senior = identifier()
    invite(HR, senior, "senior_developer")
    login(HR)
    employee = client.post(
        "/api/v1/employees",
        headers=selected,
        json={"user_id": DEV, "name": "Fixture employee", "department": "Engineering"},
    )
    assert employee.status_code == 201, employee.text
    employee_id = employee.json()["id"]
    login(DEV)
    content = io.BytesIO()
    Image.new("RGB", (8, 8)).save(content, "PNG")
    upload = client.post(
        f"/api/v1/employees/{employee_id}/identity-documents",
        headers={**selected, "Content-Type": "image/png"},
        content=content.getvalue(),
    )
    assert upload.status_code == 201, upload.text
    login(HR)
    reviewed = client.post(
        f"/api/v1/hr/identity-documents/{upload.json()['id']}/decision",
        headers=selected,
        json={"decision": "approved"},
    )
    assert reviewed.status_code == 200, reviewed.text
    plan = client.post(
        "/api/v1/hr/lifecycle",
        headers=selected,
        json={"employee_id": employee_id, "kind": "onboarding"},
    )
    assert plan.status_code == 201, plan.text
    plan_id = plan.json()["id"]
    login(OWNER)
    assert (
        client.post(
            f"/api/v1/hr/lifecycle/{plan_id}/decision",
            headers=selected,
            json={"decision": "approved"},
        ).status_code
        == 200
    )
    login(HR)
    assert (
        client.post(f"/api/v1/hr/lifecycle/{plan_id}/execute", headers=selected).json()["status"]
        == "completed"
    )
    login(DEV)
    proposal = client.post("/api/v1/projects", headers=selected, json={"name": "Journey proposal"})
    assert proposal.status_code == 201, proposal.text
    project_id = proposal.json()["id"]
    login(senior)
    assert (
        client.post(
            f"/api/v1/projects/{project_id}/decision",
            headers=selected,
            json={"decision": "reviewed"},
        ).status_code
        == 200
    )
    login(OWNER)
    assert (
        client.post(
            f"/api/v1/projects/{project_id}/decision",
            headers=selected,
            json={"decision": "approved"},
        ).status_code
        == 200
    )
    assert (
        client.post(
            f"/api/v1/projects/{project_id}/members",
            headers=selected,
            json={"user_id": senior, "manager": True},
        ).status_code
        == 201
    )
    login(senior)
    task = client.post(
        "/api/v1/tasks",
        headers=selected,
        json={"project_id": project_id, "assignee_id": DEV, "title": "Journey task"},
    )
    assert task.status_code == 201, task.text
    login(ANALYST)
    simulated = client.post("/api/v1/vader/simulator/" + identifier(), headers=selected)
    assert simulated.status_code == 200 and simulated.json()[-1]["incident_id"]
    login(OWNER)
    assert client.get("/api/v1/audit/integrity", headers=selected).json()["valid"]
