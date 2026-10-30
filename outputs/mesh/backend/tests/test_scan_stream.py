import asyncio
from datetime import timedelta

import pytest
from app import scan_stream
from app.auth import Identity, Principal
from app.models import IdentitySession, Membership, Repository, identifier, now
from conftest import ANALYST, ORG_A, ORG_B, OWNER, headers, login
from fastapi import HTTPException
from sqlalchemy.orm import sessionmaker
from test_scan_progress import prepare


class Lease:
    claimed = released = checked = 0

    def __init__(self, p=None):
        pass

    def claim(self):
        self.claimed += 1

    def check(self):
        self.checked += 1

    def release(self):
        self.released += 1


class Request:
    headers = {}
    client = None

    async def is_disconnected(self):
        return False


def setup(db, monkeypatch):
    job, _ = prepare(db, monkeypatch)
    monkeypatch.setattr(
        scan_stream, "SessionFactory", sessionmaker(db.get_bind(), expire_on_commit=False)
    )
    p = Principal(ANALYST, ORG_A, "security_analyst")
    who = Identity(ANALYST, "fixture@example.invalid", "aal2")
    return job, who, p


def test_terminal_sse_route_has_documented_snapshot_and_enforces_initial_access(
    client, db, monkeypatch
):
    job, _, _ = setup(db, monkeypatch)
    job.status, job.report = "completed", {"progress": 100}
    db.commit()
    leases = []

    def factory(p):
        lease = Lease(p)
        leases.append(lease)
        return lease

    monkeypatch.setattr("app.scan_api.StreamLease", factory)
    login(ANALYST)
    endpoint = f"/api/v1/scans/{job.id}/events"
    response = client.get(endpoint, headers=headers())
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.headers["x-accel-buffering"] == "no"
    assert response.text.count("event: scan") == 1 and '"progress":100' in response.text
    assert leases[0].claimed == leases[0].released == leases[0].checked == 1
    assert client.get(endpoint, headers=headers(ORG_B)).status_code == 404
    login(OWNER)
    assert client.get(endpoint, headers=headers()).status_code == 403


@pytest.mark.parametrize("revocation", ["membership", "repository", "role"])
def test_stream_rechecks_authorization_before_each_update_and_cleans_lease(
    db, monkeypatch, revocation
):
    job, who, p = setup(db, monkeypatch)
    lease = Lease()

    async def revoke(_):
        if revocation == "repository":
            db.get(Repository, job.repository_id).enabled = False
        else:
            member = db.get(Membership, (ORG_A, ANALYST))
            if revocation == "role":
                member.role = "owner"
            else:
                member.active = False
        db.commit()

    monkeypatch.setattr(scan_stream.asyncio, "sleep", revoke)

    async def collect():
        return [chunk async for chunk in scan_stream.events(who, p, job.id, Request(), lease)]

    chunks = asyncio.run(collect())
    assert len(chunks) == 2 and chunks[0].startswith("event: scan")
    assert chunks[1].startswith("event: end") and "unavailable" in chunks[1]
    assert lease.released == 1


def test_stream_expiry_session_revocation_and_cross_tenant_are_rejected(db, monkeypatch):
    job, _, p = setup(db, monkeypatch)
    expired = Identity(
        ANALYST, "fixture@example.invalid", "aal2", identifier(), now() - timedelta(seconds=1)
    )
    with pytest.raises(HTTPException) as error:
        scan_stream.snapshot(expired, p, job.id, Request())
    assert error.value.status_code == 401
    session_id = identifier()
    who = Identity(
        ANALYST, "fixture@example.invalid", "aal2", session_id, now() + timedelta(minutes=5)
    )
    db.add(
        IdentitySession(
            user_id=ANALYST,
            provider_session_id=session_id,
            expires_at=who.expires_at,
            revoked_at=now(),
            client_hint="fixture",
            ip_digest="0" * 64,
        )
    )
    db.commit()
    with pytest.raises(HTTPException) as error:
        scan_stream.snapshot(who, p, job.id, Request())
    assert error.value.status_code == 401
    with pytest.raises(HTTPException) as error:
        scan_stream.snapshot(
            Identity(ANALYST, "fixture@example.invalid", "aal2"),
            Principal(ANALYST, ORG_B, "security_analyst"),
            job.id,
            Request(),
        )
    assert error.value.status_code == 404


def test_stream_deadline_ends_and_releases_without_reading_database(db, monkeypatch):
    job, who, p = setup(db, monkeypatch)
    monkeypatch.setattr(scan_stream, "STREAM_SECONDS", 0)
    lease = Lease()

    async def collect():
        return [chunk async for chunk in scan_stream.events(who, p, job.id, Request(), lease)]

    assert asyncio.run(collect()) == ['event: end\ndata: {"reason":"reconnect"}\n\n']
    assert lease.checked == 0 and lease.released == 1


def test_stream_lease_failure_returns_generic_end_without_snapshot(db, monkeypatch):
    job, who, p = setup(db, monkeypatch)
    lease = Lease()

    def failed():
        raise HTTPException(409, "PRIVATE INTERNAL ERROR")

    lease.check = failed

    async def collect():
        return [chunk async for chunk in scan_stream.events(who, p, job.id, Request(), lease)]

    result = asyncio.run(collect())
    assert len(result) == 1 and "PRIVATE" not in result[0] and "event: scan" not in result[0]
    assert lease.released == 1


def test_disconnected_client_releases_without_reading_a_snapshot(db, monkeypatch):
    job, who, p = setup(db, monkeypatch)
    lease = Lease()

    class Disconnected(Request):
        async def is_disconnected(self):
            return True

    def forbidden(*args):
        raise AssertionError("Disconnected stream read the database")

    monkeypatch.setattr(scan_stream, "snapshot", forbidden)

    async def collect():
        return [chunk async for chunk in scan_stream.events(who, p, job.id, Disconnected(), lease)]

    assert asyncio.run(collect()) == [] and lease.released == 1


def test_unchanged_snapshot_uses_heartbeat_then_emits_terminal_update(db, monkeypatch):
    job, who, p = setup(db, monkeypatch)
    sequence = iter(
        [
            ('{"status":"running"}', "running"),
            ('{"status":"running"}', "running"),
            ('{"status":"completed"}', "completed"),
        ]
    )
    monkeypatch.setattr(scan_stream, "snapshot", lambda *args: next(sequence))
    monkeypatch.setattr(scan_stream, "POLL_SECONDS", 0)
    lease = Lease()

    async def collect():
        return [chunk async for chunk in scan_stream.events(who, p, job.id, Request(), lease)]

    result = asyncio.run(collect())
    assert len(result) == 3 and result[1] == ": keepalive\n\n"
    assert result[0].startswith("event: scan") and result[2].startswith("event: scan")
    assert lease.checked == 3 and lease.released == 1
