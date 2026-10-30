"""SSE progress and one validated structured result; never fabricated token deltas."""

import asyncio
from datetime import UTC
from typing import Annotated, Literal
from uuid import UUID

import anyio
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import Field, model_validator
from redis.exceptions import RedisError
from sqlalchemy import select
from starlette.concurrency import run_in_threadpool

from app.api import DB, P, Who
from app.auth import Identity, Principal, principal
from app.core.config import settings
from app.core.db import SessionFactory, assert_runtime_role, tenant_context
from app.devtrack import project_access
from app.intelligence_api import InsightOutput, hr_ai, owner_ai, project_ai, risk_ai, vader_ai
from app.models import IdentitySession, Incident, RiskAssessment, now
from app.scan_stream import StreamLease
from app.schemas import Input
from app.services import audit, scoped

router = APIRouter(prefix="/api/v1")
POLL_SECONDS = 2


class StreamInput(Input):
    purpose: Literal["owner", "hr", "devtrack", "vader", "risk"]
    target_id: UUID | None = None
    currency: Annotated[str | None, Field(pattern=r"^[A-Z]{3}$")] = None

    @model_validator(mode="after")
    def target(self):
        if (self.target_id is None) != (self.purpose in {"owner", "hr"}):
            raise ValueError("Only project, incident and risk summaries require a target ID")
        if self.currency is not None and self.purpose != "owner":
            raise ValueError("Currency selection applies only to owner summaries")
        return self


class AILease(StreamLease):
    def __init__(self, p: Principal):
        super().__init__(p)
        self.key = f"mesh:ai-stream:{p.organization_id}:{p.user_id}"

    def claim(self):
        try:
            super().claim()
        except HTTPException as error:
            if error.status_code == 429:
                raise HTTPException(
                    429,
                    "One AI stream per organization member is allowed",
                    headers={"Retry-After": "30"},
                ) from None
            if error.status_code == 503:
                raise HTTPException(503, "AI streaming is unavailable") from None
            raise


def scope(db, p: Principal, data: StreamInput):
    if data.purpose == "owner":
        p.require("finance.read")
    elif data.purpose == "hr":
        p.require("employee.read")
    elif data.purpose == "devtrack":
        p.require("project.read")
        project_access(db, p, str(data.target_id))
    else:
        p.require("security.read")
        scoped(db, Incident if data.purpose == "vader" else RiskAssessment, p, str(data.target_id))


def current(db, who: Identity, p: Principal, data: StreamInput, request: Request) -> Principal:
    if who.expires_at is not None and who.expires_at.astimezone(UTC) <= now():
        raise HTTPException(401, "Identity expired")
    # Initial authenticated_identity registers the session. Rechecks are read-only:
    # never hold its refresh/revocation advisory lock across a provider call.
    if who.session_id is not None:
        tenant_context(db, "", who.user_id)
        record = db.scalar(
            select(IdentitySession).where(
                IdentitySession.user_id == who.user_id,
                IdentitySession.provider_session_id == who.session_id,
            )
        )
        if record is None or record.revoked_at is not None:
            raise HTTPException(401, "Session unavailable or revoked")
    elif not settings().test_mode:
        raise HTTPException(401, "Provider session identifier required")
    selected = principal(who, db, UUID(p.organization_id))
    scope(db, selected, data)
    return selected


def authorize(who: Identity, p: Principal, data: StreamInput, request: Request) -> None:
    with SessionFactory.begin() as db:
        assert_runtime_role(db)
        current(db, who, p, data, request)


def produce(
    who: Identity, p: Principal, data: StreamInput, request: Request
) -> tuple[str | None, str | None]:
    try:
        with SessionFactory.begin() as db:
            assert_runtime_role(db)
            selected = current(db, who, p, data, request)
            if data.purpose == "owner":
                value = owner_ai(db, selected, data.currency)
            elif data.purpose == "hr":
                value = hr_ai(db, selected)
            else:
                if data.target_id is None:
                    raise ValueError("Missing structured summary target")
                if data.purpose == "devtrack":
                    value = project_ai(data.target_id, db, selected)
                elif data.purpose == "vader":
                    value = vader_ai(data.target_id, db, selected)
                else:
                    value = risk_ai(data.target_id, db, selected)
            payload = InsightOutput.model_validate(value).model_dump_json()
            if len(payload.encode()) > 32768:
                raise ValueError("Structured insight exceeded stream bound")
        # Usage commit is independent of the response. A disconnected client does
        # not erase a completed billable call or cause automatic regeneration.
        return payload, None
    except HTTPException as error:
        return (
            None,
            "quota_or_policy_limit" if error.status_code == 429 else "generation_unavailable",
        )
    except Exception:
        return None, "generation_unavailable"


def renew_during_drain(lease: AILease) -> bool:
    try:
        lease.check()
        return True
    except (HTTPException, RedisError):
        # Delivery has stopped. Do not interrupt accounting for an already
        # dispatched request; a lost lease independently expires in Redis.
        return False


async def events(who: Identity, p: Principal, data: StreamInput, request: Request, lease: AILease):
    task = None
    try:
        if await request.is_disconnected():
            return
        yield 'event: state\ndata: {"state":"generating","contract":"mesh-ai-sse-v1"}\n\n'
        if await request.is_disconnected():
            return
        task = asyncio.create_task(asyncio.to_thread(produce, who, p, data, request))
        while not task.done():
            await asyncio.wait({task}, timeout=POLL_SECONDS)
            if await request.is_disconnected():
                return
            try:
                await run_in_threadpool(lease.check)
                await run_in_threadpool(authorize, who, p, data, request)
            except Exception:
                yield 'event: error\ndata: {"code":"authorization_or_dependency_unavailable","automatic_retry":false}\n\n'
                return
            if not task.done():
                yield ": keepalive\n\n"
        payload, error = task.result()
        await run_in_threadpool(authorize, who, p, data, request)
        if await request.is_disconnected():
            return
        if error:
            yield f'event: error\ndata: {{"code":"{error}","automatic_retry":false}}\n\n'
        else:
            yield f"event: result\ndata: {payload}\n\n"
    except Exception:
        yield 'event: error\ndata: {"code":"authorization_or_dependency_unavailable","automatic_retry":false}\n\n'
    finally:
        # Python threads cannot cancel an in-flight provider POST. Drain it and
        # retain the lease until accounting completes, without sending more data.
        with anyio.CancelScope(shield=True):
            try:
                if task is not None:
                    while not task.done():
                        await asyncio.wait({task}, timeout=POLL_SECONDS)
                        await run_in_threadpool(renew_during_drain, lease)
                    task.result()  # produce always returns a sanitized outcome.
            finally:
                await run_in_threadpool(lease.release)


@router.post(
    "/ai/stream",
    response_class=StreamingResponse,
    responses={200: {"content": {"text/event-stream": {"schema": {"type": "string"}}}}},
)
def stream(data: StreamInput, request: Request, db: DB, p: P, who: Who):
    """SSE state/heartbeat/result/error. Result is a complete InsightOutput, never partial model JSON.

    POST once; no automatic reconnect, replay or regeneration after disconnect.
    Generation is advisory and uses the same minimized context and quota policy as JSON APIs.
    """
    scope(db, p, data)
    audit(
        db, p, "ai.stream.requested", str(data.target_id) if data.target_id else p.organization_id
    )
    lease = AILease(p)
    lease.claim()
    return StreamingResponse(
        events(who, p, data, request, lease),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )
