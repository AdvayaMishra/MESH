from datetime import timedelta

import httpx
import pytest
from app.auth import Principal
from app.core.config import settings
from app.documents import PrivateStorage, reconcile_orphans
from app.models import Employee, IdentityDocument, identifier, now
from conftest import DEV, ORG_A
from fastapi import HTTPException
from pydantic import SecretStr


def test_reconciliation_preserves_referenced_recent_updated_and_unknown_age_files(db):
    employee, reference, orphan, recent, updated = [identifier() for _ in range(5)]
    db.add(
        Employee(id=employee, organization_id=ORG_A, user_id=DEV, name="Fixture", department="Test")
    )
    db.flush()
    old = (now() - timedelta(days=3)).isoformat()
    current = now().isoformat()
    db.add(
        IdentityDocument(
            id=reference,
            organization_id=ORG_A,
            employee_id=employee,
            storage_key=f"{ORG_A}/{employee}/{reference}",
            media_type="image/png",
            digest="0" * 64,
            expires_at=now() + timedelta(days=30),
        )
    )
    db.commit()
    deleted = []
    prefixes = []

    class Storage:
        def list(self, prefix, offset):
            prefixes.append(prefix)
            if prefix == ORG_A + "/":
                return [{"name": employee, "id": None}, {"name": "../../other-tenant", "id": None}]
            return [
                {"name": name, "id": identifier(), "created_at": created, "updated_at": modified}
                for name, created, modified in (
                    (reference, old, old),
                    (orphan, old, old),
                    (recent, current, current),
                    (updated, old, current),
                    (identifier(), "invalid", old),
                )
            ]

        def delete(self, key):
            deleted.append(key)

    p = Principal("retention-worker", ORG_A, "system")
    dry = reconcile_orphans(db, p, storage=Storage())
    assert dry["candidates"] == 1 and dry["removed"] == 0 and not deleted
    result = reconcile_orphans(db, p, storage=Storage(), apply=True)
    assert result["removed"] == 1
    assert deleted == [f"{ORG_A}/{employee}/{orphan}"]
    assert all(prefix.startswith(ORG_A + "/") for prefix in prefixes)


def test_reconciliation_never_deletes_on_incomplete_inventory(db):
    employee = identifier()
    deleted = []

    class Storage:
        def list(self, prefix, offset):
            if prefix == ORG_A + "/":
                return [{"name": employee, "id": None}] * 100
            return [
                {
                    "name": identifier(),
                    "id": identifier(),
                    "created_at": "2020-01-01T00:00:00Z",
                    "updated_at": "2020-01-01T00:00:00Z",
                }
            ] * 100

        def delete(self, key):
            deleted.append(key)

    with pytest.raises(HTTPException) as exc:
        reconcile_orphans(db, Principal("worker", ORG_A, "system"), storage=Storage(), apply=True)
    assert exc.value.status_code == 503 and deleted == []


def test_reconciliation_rejects_a_short_upload_grace_period(db):
    with pytest.raises(HTTPException) as exc:
        reconcile_orphans(db, Principal("worker", ORG_A, "system"), grace_hours=1)
    assert exc.value.status_code == 422


@pytest.mark.parametrize(
    "signed",
    [
        "https://attacker.invalid/object/sign/mesh-identity/a/b/c?token=secret",
        "/object/sign/mesh-identity/a/b/other?token=secret",
        "/object/sign/mesh-identity/a/b/c",
        "http://[",
        None,
    ],
)
def test_storage_never_returns_a_malformed_or_different_object_link(monkeypatch, signed):
    monkeypatch.setattr(settings(), "supabase_url", "https://storage.example.org")
    monkeypatch.setattr(settings(), "supabase_storage_key", SecretStr("fixture-key"))
    with httpx.Client(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json={"signedURL": signed}))
    ) as client:
        with pytest.raises(HTTPException) as exc:
            PrivateStorage(client).sign(f"{ORG_A}/{identifier()}/{identifier()}")
    assert exc.value.status_code == 503


def test_storage_inventory_rejects_an_invalid_response_shape(monkeypatch):
    monkeypatch.setattr(settings(), "supabase_url", "https://storage.example.org")
    monkeypatch.setattr(settings(), "supabase_storage_key", SecretStr("fixture-key"))
    with httpx.Client(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json={"items": []}))
    ) as client:
        with pytest.raises(HTTPException) as exc:
            PrivateStorage(client).list(ORG_A + "/")
    assert exc.value.status_code == 503


def test_new_supabase_secret_keys_use_only_the_apikey_header(monkeypatch):
    monkeypatch.setattr(settings(), "supabase_url", "https://storage.example.org")
    monkeypatch.setattr(
        settings(), "supabase_storage_key", SecretStr("sb_secret_fixture_backend_key")
    )

    def handler(request):
        assert request.headers["apikey"] == "sb_secret_fixture_backend_key"
        assert "authorization" not in request.headers
        return httpx.Response(200, json=[])

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        assert PrivateStorage(client).list(ORG_A + "/") == []


def test_publishable_key_cannot_be_used_as_private_storage_authority(monkeypatch):
    monkeypatch.setattr(settings(), "supabase_url", "https://storage.example.org")
    monkeypatch.setattr(settings(), "supabase_storage_key", SecretStr("sb_publishable_fixture"))
    with pytest.raises(HTTPException) as exc:
        PrivateStorage().list(ORG_A + "/")
    assert exc.value.status_code == 503
