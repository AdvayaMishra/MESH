"""Bounded scan snapshots; no database connection remains open between updates."""

import asyncio
import hashlib
import secrets
import time
from uuid import UUID

from fastapi import HTTPException, Request
from redis import Redis
from redis.exceptions import RedisError
from sqlalchemy.exc import SQLAlchemyError
from starlette.concurrency import run_in_threadpool

from app.auth import Identity, Principal, principal
from app.core.config import settings
from app.core.db import SessionFactory, assert_runtime_role
from app.devtrack import repository_access
from app.enterprise_schemas import ScanOutput
from app.models import ScanJob, now
from app.services import scoped
from app.sessions import track_identity

STREAM_SECONDS = 30
POLL_SECONDS = 2
TERMINAL = {"completed", "dead_letter", "failed", "cancelled"}


class StreamLease:
    def __init__(self, p: Principal):
        self.client = Redis.from_url(
            settings().redis_url, socket_timeout=2, socket_connect_timeout=2
        )
        self.key = f"mesh:scan-stream:{p.organization_id}:{p.user_id}"
        self.token = secrets.token_hex(16)

    def claim(self):
        try:
            if not self.client.set(self.key, self.token, nx=True, ex=60):
                raise HTTPException(
                    429,
                    "One scan stream per organization member is allowed",
                    headers={"Retry-After": "30"},
                )
        except RedisError:
            self.client.close()
            raise HTTPException(503, "Scan streaming is unavailable") from None
        except HTTPException:
            self.client.close()
            raise

    def check(self):
        if not self.client.eval(
            "if redis.call('GET',KEYS[1]) == ARGV[1] then return redis.call('EXPIRE',KEYS[1],60) else return 0 end",
            1,
            self.key,
            self.token,
        ):
            raise HTTPException(409, "Scan stream lease expired")

    def release(self):
        try:
            self.client.eval(
                "if redis.call('GET',KEYS[1]) == ARGV[1] then return redis.call('DEL',KEYS[1]) else return 0 end",
                1,
                self.key,
                self.token,
            )
        except RedisError:
            pass  # A crashed/disconnected stream's lease expires independently.
        finally:
            self.client.close()


def snapshot(who: Identity, p: Principal, job_id: str, request: Request) -> tuple[str, str]:
    if who.expires_at is not None and who.expires_at <= now():
        raise HTTPException(401, "Identity expired")
    with SessionFactory.begin() as db:
        assert_runtime_role(db)
        track_identity(db, who, request)
        current = principal(who, db, UUID(p.organization_id))
        current.require("repository.read")
        job = scoped(db, ScanJob, current, job_id)
        repository = repository_access(db, current, job.repository_id)
        if not repository.enabled:
            raise HTTPException(403, "Repository authorization was revoked")
        payload = ScanOutput.model_validate(job).model_dump_json()
        if len(payload.encode()) > 131072:
            raise HTTPException(503, "Scan snapshot exceeds stream limit")
        return payload, job.status


async def events(who: Identity, p: Principal, job_id: str, request: Request, lease: StreamLease):
    deadline, previous = time.monotonic() + STREAM_SECONDS, None
    try:
        while time.monotonic() < deadline:
            if await request.is_disconnected():
                return
            try:
                payload, status = await run_in_threadpool(snapshot, who, p, job_id, request)
                await run_in_threadpool(lease.check)
            except (HTTPException, SQLAlchemyError, RedisError, ValueError):
                yield 'event: end\ndata: {"reason":"authorization_or_dependency_unavailable"}\n\n'
                return
            digest = hashlib.sha256(payload.encode()).hexdigest()
            if digest != previous:
                yield f"event: scan\nid: {digest}\ndata: {payload}\n\n"
                previous = digest
            else:
                yield ": keepalive\n\n"
            if status in TERMINAL:
                return
            await asyncio.sleep(POLL_SECONDS)
        yield 'event: end\ndata: {"reason":"reconnect"}\n\n'
    finally:
        await run_in_threadpool(lease.release)
