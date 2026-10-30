import hashlib
import hmac
import json
from datetime import timedelta

from app.core.config import settings
from app.models import Repository, ScanJob, WebhookDelivery, identifier, now
from conftest import ANALYST, ORG_A, ORG_B, OWNER
from pydantic import SecretStr
from sqlalchemy import select

SECRET = "fixture-webhook-secret-" + "a" * 32


def configure(monkeypatch, actor=ANALYST):
    monkeypatch.setattr(settings(), "github_webhook_secret", SecretStr(SECRET))
    monkeypatch.setattr(settings(), "github_webhook_previous_secret", None)
    monkeypatch.setattr(settings(), "github_installations", {"1": ORG_A})
    monkeypatch.setattr(settings(), "github_scan_actors", {ORG_A: actor})


def send(client, event, payload, delivery=None, secret=SECRET, **extra_headers):
    body = json.dumps(payload, separators=(",", ":")).encode()
    return client.post(
        "/api/v1/webhooks/github",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-GitHub-Delivery": delivery or identifier(),
            "X-GitHub-Event": event,
            "X-Hub-Signature-256": "sha256="
            + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest(),
            **extra_headers,
        },
    )


def repositories(db):
    records = [
        Repository(
            id=identifier(),
            organization_id=org,
            full_name="org/repo",
            installation_id=1,
            enabled=True,
        )
        for org in (ORG_A, ORG_B)
    ]
    db.add_all(records)
    db.commit()
    return records


def test_signed_push_queues_once_and_replay_cannot_change_commit_or_store_payload(
    client, db, monkeypatch
):
    configure(monkeypatch)
    repositories(db)
    delivery = identifier()
    payload = {
        "installation": {"id": 1},
        "repository": {"full_name": "org/repo"},
        "after": "a" * 40,
        "source_secret": "MUST_NOT_BE_STORED",
    }
    response = send(client, "push", payload, delivery)
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "scan_queued"
    again = send(client, "push", payload, identifier())
    assert again.json()["duplicate"] is True
    assert again.json()["scan_id"] == response.json()["scan_id"]
    conflict = send(client, "push", {**payload, "after": "b" * 40}, delivery)
    assert conflict.status_code == 409
    assert len(db.scalars(select(ScanJob)).all()) == 1
    receipt = db.scalar(select(WebhookDelivery))
    assert "MUST_NOT_BE_STORED" not in json.dumps(receipt.result)
    assert receipt.organization_id == ORG_A


def test_installation_revocation_fences_running_jobs_and_never_crosses_tenants(
    client, db, monkeypatch
):
    configure(monkeypatch)
    first, foreign = repositories(db)
    job = ScanJob(
        organization_id=ORG_A,
        repository_id=first.id,
        requested_by=ANALYST,
        commit_sha="a" * 40,
        request_key="fixture-running",
        status="running",
        lease_until=now() + timedelta(minutes=10),
    )
    db.add(job)
    db.commit()
    response = send(client, "installation", {"installation": {"id": 1}, "action": "suspend"})
    assert response.status_code == 200, response.text
    assert not db.get(Repository, first.id).enabled and db.get(Repository, foreign.id).enabled
    db.refresh(job)
    assert job.status == "cancelled" and job.lease_until is None


def test_empty_removal_inventory_revokes_unknown_local_repository_grants(client, db, monkeypatch):
    configure(monkeypatch)
    first, foreign = repositories(db)
    response = send(
        client,
        "installation_repositories",
        {
            "installation": {"id": 1},
            "action": "removed",
            "repositories_removed": [],
        },
    )
    assert response.status_code == 200 and response.json()["status"] == "repositories_revoked"
    assert not db.get(Repository, first.id).enabled and db.get(Repository, foreign.id).enabled


def test_signature_and_operator_binding_are_required_regardless_of_tenant_header(
    client, db, monkeypatch
):
    configure(monkeypatch)
    first, _ = repositories(db)
    payload = {"installation": {"id": 1}, "action": "deleted"}
    assert send(client, "installation", payload, secret="wrong-secret").status_code == 401
    ignored = send(
        client,
        "installation",
        {**payload, "installation": {"id": 999}},
        **{"X-Organization-ID": ORG_A},
    )
    assert ignored.json()["status"] == "ignored_unbound_installation"
    assert db.get(Repository, first.id).enabled
    assert db.scalars(select(WebhookDelivery)).all() == []


def test_webhook_secret_rotation_accepts_the_previous_key_without_automatic_grants(
    client, db, monkeypatch
):
    configure(monkeypatch)
    first, _ = repositories(db)
    first.enabled = False
    db.commit()
    monkeypatch.setattr(settings(), "github_webhook_previous_secret", SecretStr(SECRET))
    monkeypatch.setattr(settings(), "github_webhook_secret", SecretStr("new-" + "b" * 40))
    response = send(client, "installation", {"installation": {"id": 1}, "action": "unsuspend"})
    assert response.json()["status"] == "owner_review_required"
    assert not db.get(Repository, first.id).enabled


def test_owner_role_is_not_silently_promoted_to_automated_scanner(client, db, monkeypatch):
    configure(monkeypatch, actor=OWNER)
    repositories(db)
    response = send(
        client,
        "push",
        {"installation": {"id": 1}, "repository": {"full_name": "org/repo"}, "after": "a" * 40},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "ignored_unauthorized_scan_actor"
    assert db.scalars(select(ScanJob)).all() == []
