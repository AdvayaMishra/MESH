"""Public error schemas; rejected input values are deliberately absent."""

from http import HTTPStatus
from typing import Any

from pydantic import BaseModel, ConfigDict


class ErrorDetail(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str
    message: str
    request_id: str | None = None
    fields: list[str] | None = None


class ErrorEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")
    error: ErrorDetail


ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    status: {
        "model": ErrorEnvelope,
        "description": HTTPStatus(status).phrase,
    }
    for status in (400, 401, 403, 404, 409, 413, 422, 429, 500, 503)
}
