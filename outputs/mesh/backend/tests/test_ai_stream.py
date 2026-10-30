import asyncio
import sqlite3
import threading
from datetime import timedelta

import pytest
from app import ai_stream
from app.auth import Identity, Principal
from app.models import AIUsage, IdentitySession, Membership, identifier, now
from conftest import HR, ORG_A, OWNER, headers, login
from fastapi import HTTPException
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import Session, sessionmaker


class Lease:
    def __init__(self, *_):
        self.claimed = self.released = self.checked = 0

    def claim(self):
        self.claimed += 1

    def check(self):
        self.checked += 1

    def release(self):
        self.released += 1


class Request:
    headers = {}
    client = None
    disconnected = False

    async def is_disconnected(self):
        return self.disconnected


@pytest.fixture
def db(db, tmp_path):
    # Concurrent producer/recheck sessions need independent connections. StaticPool
    # shares one SQLite transaction and can spuriously roll back another session.
    db.commit()
    path = tmp_path / "ai-stream.sqlite3"
    raw = db.get_bind().raw_connection()
    try:
        with sqlite3.connect(path) as target:
            raw.driver_connection.backup(target)
    finally:
        raw.close()
    engine = create_engine("sqlite:///" + str(path), connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def foreign_keys(connection, _):
        connection.execute("PRAGMA foreign_keys=ON")

    try:
        with Session(engine, expire_on_commit=False) as database:
            yield database
    finally:
        engine.dispose()


@pytest.fixture
def configured(db, monkeypatch):
    monkeypatch.setattr(
        ai_stream, "SessionFactory", sessionmaker(db.get_bind(), expire_on_commit=False)
    )
    monkeypatch.setattr(ai_stream, "AILease", Lease)
    monkeypatch.setattr(ai_stream, "POLL_SECONDS", 0.01)


def test_real_local_summary_sse_has_one_validated_result_and_durable_usage(client, db, configured):
    login(HR)
    response = client.post("/api/v1/ai/stream", headers=headers(), json={"purpose": "hr"})
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("text/event-stream")
    assert (
        response.headers["x-accel-buffering"] == "no"
        and response.headers["cache-control"] == "no-store"
    )
    assert response.text.count("event: result") == 1
    assert '"contract":"mesh-ai-sse-v1"' in response.text
    assert '"provider":"local-deterministic"' in response.text
    assert "event: delta" not in response.text
    assert db.scalar(select(func.count()).select_from(AIUsage)) == 1
    assert (
        client.post("/api/v1/ai/stream", headers=headers(), json={"purpose": "owner"}).status_code
        == 403
    )
    login(OWNER)
    assert (
        client.post("/api/v1/ai/stream", headers=headers(), json={"purpose": "hr"}).status_code
        == 403
    )


@pytest.mark.parametrize(
    "payload",
    [
        {"purpose": "devtrack"},
        {"purpose": "hr", "target_id": identifier()},
        {"purpose": "arbitrary", "context": "private input"},
    ],
)
def test_stream_never_accepts_arbitrary_context_or_ambiguous_target(client, configured, payload):
    login(HR)
    assert client.post("/api/v1/ai/stream", headers=headers(), json=payload).status_code == 422


def collect(request, lease, who=None):
    async def consume():
        return [
            item
            async for item in ai_stream.events(
                who or Identity(HR, "fixture@example.invalid"),
                Principal(HR, ORG_A, "hr"),
                ai_stream.StreamInput(purpose="hr"),
                request,
                lease,
            )
        ]

    return asyncio.run(consume())


def test_disconnect_before_generation_makes_no_model_call(db, configured, monkeypatch):
    called = []
    monkeypatch.setattr(ai_stream, "produce", lambda *_: called.append(True))
    request, lease = Request(), Lease()
    request.disconnected = True
    assert collect(request, lease) == []
    assert not called and lease.released == 1
    assert db.scalar(select(func.count()).select_from(AIUsage)) == 0


@pytest.mark.parametrize("stop", ["disconnect", "revoke"])
def test_completed_usage_survives_disconnect_and_revoked_result_is_not_delivered(
    db, configured, monkeypatch, stop
):
    real_produce = ai_stream.produce
    request, lease = Request(), Lease()

    def produce(*args):
        value = real_produce(*args)
        if stop == "disconnect":
            request.disconnected = True
        else:
            with ai_stream.SessionFactory.begin() as session:
                session.get(Membership, (ORG_A, HR)).active = False
        return value

    monkeypatch.setattr(ai_stream, "produce", produce)
    messages = collect(request, lease)
    assert not any("event: result" in item for item in messages)
    assert lease.released == 1
    assert db.scalar(select(func.count()).select_from(AIUsage)) == 1
    if stop == "revoke":
        assert any("authorization_or_dependency_unavailable" in item for item in messages)


def test_failed_generation_has_sanitized_error_and_does_not_automatically_retry(
    db, configured, monkeypatch
):
    called = []

    def fail(*_):
        called.append(True)
        raise HTTPException(503, "PRIVATE DIAGNOSTIC")

    monkeypatch.setattr(ai_stream, "hr_ai", fail)
    lease = Lease()
    output = "".join(collect(Request(), lease))
    assert len(called) == 1 and '"automatic_retry":false' in output
    assert "generation_unavailable" in output and "PRIVATE" not in output
    assert lease.released == 1


@pytest.mark.parametrize("condition", ["expired", "revoked_session", "role_changed"])
def test_delivery_rechecks_session_expiry_denylist_and_role(db, configured, condition):
    who = Identity(
        HR,
        "fixture@example.invalid",
        "aal2",
        session_id=identifier(),
        expires_at=now() + timedelta(minutes=5),
    )
    record = IdentitySession(
        user_id=HR,
        provider_session_id=who.session_id,
        client_hint="fixture",
        ip_digest="0" * 64,
        expires_at=who.expires_at,
    )
    db.add(record)
    db.commit()
    if condition == "expired":
        who = Identity(HR, "fixture@example.invalid", expires_at=now() - timedelta(seconds=1))
    elif condition == "revoked_session":
        record.revoked_at = now()
        db.commit()
    else:
        db.get(Membership, (ORG_A, HR)).role = "owner"
        db.commit()
    with pytest.raises(HTTPException):
        ai_stream.authorize(
            who, Principal(HR, ORG_A, "hr"), ai_stream.StreamInput(purpose="hr"), Request()
        )


def test_cancelled_consumer_drains_one_call_commits_usage_and_releases_lease(
    db, configured, monkeypatch
):
    started, finish = threading.Event(), threading.Event()
    real_produce = ai_stream.produce
    lease = Lease()

    def produce(*args):
        started.set()
        if not finish.wait(timeout=3):
            return None, "fixture_timeout"
        return real_produce(*args)

    monkeypatch.setattr(ai_stream, "produce", produce)

    async def scenario():
        async def consume():
            async for _ in ai_stream.events(
                Identity(HR, "fixture@example.invalid"),
                Principal(HR, ORG_A, "hr"),
                ai_stream.StreamInput(purpose="hr"),
                Request(),
                lease,
            ):
                pass

        task = asyncio.create_task(consume())
        while not started.is_set():
            await asyncio.sleep(0.001)
        task.cancel()
        asyncio.get_running_loop().call_later(0.02, finish.set)
        with pytest.raises(asyncio.CancelledError):
            await task

    try:
        asyncio.run(scenario())
    finally:
        finish.set()
    assert lease.released == 1
    assert db.scalar(select(func.count()).select_from(AIUsage)) == 1
