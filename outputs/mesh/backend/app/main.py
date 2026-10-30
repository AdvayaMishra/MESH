import time
import uuid
from contextlib import asynccontextmanager
from typing import cast

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from redis import Redis
from redis.exceptions import RedisError
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from starlette.concurrency import run_in_threadpool
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.account_api import router as account_router
from app.ai_accounting_pool import close as close_ai_accounting
from app.ai_receipts_api import router as ai_receipts_router
from app.ai_stream import router as ai_stream_router
from app.ai_usage import router as ai_usage_router
from app.api import router
from app.auth_limits import AUTH_PATHS, account_key
from app.billing_api import router as billing_router
from app.cloud_integration_api import router as cloud_integration_router
from app.cloud_jobs import router as cloud_jobs_router
from app.core.config import settings
from app.core.db import SessionFactory, assert_runtime_role
from app.core.logging import configure
from app.core.metrics import record, render
from app.correlation_api import router as correlation_router
from app.document_api import router as document_router
from app.enterprise_api import router as enterprise_router
from app.error_contract import ERROR_RESPONSES
from app.github_webhook import router as github_webhook_router
from app.intelligence_api import router as intelligence_router
from app.investigation_api import router as investigation_router
from app.mfa_api import router as mfa_router
from app.payroll import router as payroll_router
from app.project_governance_api import router as governance_router
from app.risk_api import router as risk_router
from app.scan_api import router as scan_router
from app.session_api import router as session_router
from app.workflow_api import router as workflow_router
from app.workforce_api import router as workforce_router


@asynccontextmanager
async def lifespan(application: FastAPI):
    try:
        yield
    finally:
        close_ai_accounting()


app = FastAPI(
    lifespan=lifespan,
    title="MESH Backend",
    version="0.1.0",
    responses=ERROR_RESPONSES,
    description="Partial backend implementation. See IMPLEMENTATION_STATUS.md for unsupported features.",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings().cors_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type", "X-Organization-ID"],
    expose_headers=["X-Request-ID"],
)
app.include_router(router)
app.include_router(enterprise_router)
app.include_router(scan_router)
app.include_router(document_router)
app.include_router(intelligence_router)
app.include_router(account_router)
app.include_router(payroll_router)
app.include_router(workflow_router)
app.include_router(workforce_router)
app.include_router(investigation_router)
app.include_router(session_router)
app.include_router(github_webhook_router)
app.include_router(governance_router)
app.include_router(risk_router)
app.include_router(cloud_jobs_router)
app.include_router(mfa_router)
app.include_router(ai_stream_router)
app.include_router(ai_usage_router)
app.include_router(ai_receipts_router)
app.include_router(correlation_router)
app.include_router(billing_router)
app.include_router(cloud_integration_router)
logger = configure()
redis_client = Redis.from_url(settings().redis_url, socket_connect_timeout=2, socket_timeout=2)


def finish_response(request: Request, response: Response, start: float) -> Response:
    record(request.method, response.status_code, time.monotonic() - start)
    response.headers.update(
        {
            "X-Request-ID": request.state.request_id,
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "no-store",
            "Referrer-Policy": "no-referrer",
        }
    )
    if settings().environment == "production":
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    logger.info(
        "request",
        extra={
            "request_id": request.state.request_id,
            "method": request.method,
            "status": response.status_code,
            "duration_ms": round((time.monotonic() - start) * 1000),
        },
    )
    return response


@app.middleware("http")
async def controls(request: Request, call_next):
    request.state.request_id = str(uuid.uuid4())
    start = time.monotonic()
    request.state.started_at = start
    if request.url.path.startswith("/api/"):
        if not settings().test_mode:
            try:
                # Proxy headers are deliberately ignored; deploy behind a configured trusted proxy.
                key = f"mesh:rate:{request.client.host if request.client else 'unknown'}:{int(time.time()) // 60}"
                count = await run_in_threadpool(
                    lambda: cast(
                        int,
                        redis_client.eval(
                            "local c=redis.call('INCR',KEYS[1]); if c==1 then redis.call('EXPIRE',KEYS[1],120) end; return c",
                            1,
                            key,
                        ),
                    )
                )
                if count > 120:
                    return finish_response(
                        request,
                        JSONResponse(
                            {
                                "error": {
                                    "code": "rate_limited",
                                    "message": "Request rate exceeded",
                                    "request_id": request.state.request_id,
                                }
                            },
                            status_code=429,
                            headers={"Retry-After": "60"},
                        ),
                        start,
                    )
            except RedisError:
                return finish_response(
                    request,
                    JSONResponse(
                        {
                            "error": {
                                "code": "unavailable",
                                "message": "Rate limiter unavailable",
                                "request_id": request.state.request_id,
                            }
                        },
                        status_code=503,
                    ),
                    start,
                )
        # Bound actual bytes, including chunked bodies, rather than trusting Content-Length.
        body = bytearray()
        maximum = (
            2097152
            if request.url.path.endswith("/identity-documents")
            else 1048576
            if request.url.path == "/api/v1/webhooks/github"
            else settings().max_request_bytes
        )
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body) > maximum:
                return finish_response(
                    request,
                    JSONResponse(
                        {
                            "error": {
                                "code": "request_too_large",
                                "message": "Request body too large",
                                "request_id": request.state.request_id,
                            }
                        },
                        status_code=413,
                    ),
                    start,
                )
        request._body = bytes(body)
        if not settings().test_mode and request.method == "POST" and request.url.path in AUTH_PATHS:
            try:
                private_key = account_key(bytes(body))
                if private_key:
                    attempts = await run_in_threadpool(
                        lambda: cast(
                            int,
                            redis_client.eval(
                                "local c=redis.call('INCR',KEYS[1]); if c==1 then redis.call('EXPIRE',KEYS[1],120) end; return c",
                                1,
                                private_key,
                            ),
                        )
                    )
                    if attempts > 20:
                        return finish_response(
                            request,
                            JSONResponse(
                                {
                                    "error": {
                                        "code": "rate_limited",
                                        "message": "Authentication attempt rate exceeded",
                                        "request_id": request.state.request_id,
                                    }
                                },
                                status_code=429,
                                headers={"Retry-After": "60"},
                            ),
                            start,
                        )
            except (RedisError, RuntimeError):
                return finish_response(
                    request,
                    JSONResponse(
                        {
                            "error": {
                                "code": "unavailable",
                                "message": "Authentication protection unavailable",
                                "request_id": request.state.request_id,
                            }
                        },
                        status_code=503,
                    ),
                    start,
                )
    response = await call_next(request)
    return finish_response(request, response, start)


@app.exception_handler(StarletteHTTPException)
async def http_error(request: Request, exc: StarletteHTTPException):
    return JSONResponse(
        {
            "error": {
                "code": f"http_{exc.status_code}",
                "message": exc.detail,
                "request_id": getattr(request.state, "request_id", None),
            }
        },
        status_code=exc.status_code,
        headers=exc.headers,
    )


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError):
    # Pydantic error inputs can contain credentials. Never return rejected input values.
    return JSONResponse(
        {
            "error": {
                "code": "validation_error",
                "message": "Request validation failed",
                "fields": [".".join(map(str, error["loc"])) for error in exc.errors()],
                "request_id": getattr(request.state, "request_id", None),
            }
        },
        status_code=422,
    )


@app.exception_handler(IntegrityError)
async def conflict(request: Request, exc: IntegrityError):
    return JSONResponse(
        {
            "error": {
                "code": "conflict",
                "message": "Record conflicts with existing data",
                "request_id": getattr(request.state, "request_id", None),
            }
        },
        status_code=409,
    )


@app.exception_handler(Exception)
async def unexpected(request: Request, exc: Exception):
    # Do not log exceptions that may contain SQL parameters or provider tokens.
    logger.error(
        "unhandled_error",
        extra={
            "request_id": getattr(request.state, "request_id", None),
            "exception_type": type(exc).__name__,
        },
    )
    response = JSONResponse(
        {
            "error": {
                "code": "internal_error",
                "message": "Request failed",
                "request_id": getattr(request.state, "request_id", None),
            }
        },
        status_code=500,
    )
    return finish_response(
        request, response, getattr(request.state, "started_at", time.monotonic())
    )


@app.get("/health/live")
def live():
    return {"status": "alive"}


@app.get("/metrics", response_class=Response, include_in_schema=False)
def metrics():
    return Response(render(), media_type="text/plain; version=0.0.4")


@app.get("/health/ready")
def ready():
    try:
        with SessionFactory() as db:
            assert_runtime_role(db)
            db.execute(text("SELECT 1 FROM organizations LIMIT 1"))
        redis_client.ping()
    except (SQLAlchemyError, RedisError):
        raise HTTPException(503, "Dependencies unavailable") from None
    if not settings().supabase_url:
        raise HTTPException(503, "Identity provider is not configured")
    return {"status": "ready"}
