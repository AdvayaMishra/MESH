import pytest
from app.core.config import settings
from app.core.db import session
from app.error_contract import ErrorEnvelope
from app.main import app
from conftest import headers
from redis.exceptions import RedisError
from sqlalchemy.exc import IntegrityError


def test_openapi_documents_sanitized_error_envelope_for_every_api():
    spec = app.openapi()
    for path, operations in spec["paths"].items():
        if not path.startswith("/api/"):
            continue
        for method, operation in operations.items():
            if method not in {"get", "post", "patch", "put", "delete"}:
                continue
            for code in (401, 403, 404, 409, 413, 422, 429, 500, 503):
                schema = operation["responses"][str(code)]["content"]["application/json"]["schema"]
                assert schema["$ref"] == "#/components/schemas/ErrorEnvelope"
    assert "HTTPValidationError" not in spec["components"]["schemas"]
    assert (
        "text/event-stream"
        in spec["paths"]["/api/v1/ai/stream"]["post"]["responses"]["200"]["content"]
    )


@pytest.mark.parametrize(
    "path,status",
    [
        ("/api/v1/contract-route-does-not-exist", 404),
        ("/api/v1/projects?limit=private-invalid-value", 422),
    ],
)
def test_http_errors_match_public_schema_without_rejected_values(client, path, status):
    response = client.get(path, headers=headers())
    assert response.status_code == status
    error = ErrorEnvelope.model_validate(response.json()).error
    assert error.request_id == response.headers["x-request-id"]
    assert "private-invalid-value" not in response.text
    if status == 422:
        assert "query.limit" in error.fields


def test_early_body_limit_matches_documented_error(client, monkeypatch):
    monkeypatch.setattr(settings(), "max_request_bytes", 8)
    response = client.post("/api/v1/contract-route-does-not-exist", content=b"123456789")
    assert response.status_code == 413
    parsed = ErrorEnvelope.model_validate(response.json()).error
    assert parsed.code == "request_too_large"
    assert parsed.request_id == response.headers["x-request-id"]
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.parametrize("outage", [False, True])
def test_rate_limit_and_dependency_errors_match_public_schema(client, monkeypatch, outage):
    import app.main as main

    monkeypatch.setattr(settings(), "test_mode", False)

    class RedisFixture:
        def eval(self, *args):
            if outage:
                raise RedisError("private Redis details")
            return 121

    monkeypatch.setattr(main, "redis_client", RedisFixture())
    response = client.get("/api/v1/contract-route-does-not-exist")
    assert response.status_code == (503 if outage else 429)
    assert ErrorEnvelope.model_validate(response.json()).error.code == (
        "unavailable" if outage else "rate_limited"
    )
    assert "private Redis details" not in response.text
    assert response.json()["error"]["request_id"] == response.headers["x-request-id"]
    if not outage:
        assert response.headers["retry-after"] == "60"


@pytest.mark.parametrize("failure", ["unexpected", "conflict"])
def test_database_and_unexpected_errors_match_schema_and_redact_exceptions(client, failure):
    original = app.dependency_overrides[session]

    def failed_session():
        if failure == "conflict":
            raise IntegrityError(
                "private SQL statement",
                {"password": "private-password"},
                Exception("private connection details"),
            )
        raise RuntimeError("private connection password must not escape")

    app.dependency_overrides[session] = failed_session
    try:
        response = client.get("/api/v1/projects", headers=headers())
        assert response.status_code == (500 if failure == "unexpected" else 409)
        parsed = ErrorEnvelope.model_validate(response.json()).error
        assert parsed.code == ("internal_error" if failure == "unexpected" else "conflict")
        assert parsed.request_id == response.headers["x-request-id"]
        assert response.headers["cache-control"] == "no-store"
        assert response.headers["x-content-type-options"] == "nosniff"
        assert "password" not in response.text and "connection" not in response.text
    finally:
        app.dependency_overrides[session] = original
