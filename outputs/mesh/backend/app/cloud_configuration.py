"""Local-only binding diagnostics; inspecting setup never resolves SDK credentials."""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel

from app.cloud_identity import AWSAccountIdentity
from app.core.config import settings

Capability = Literal["posture", "billing"]


class ConnectionStatus(BaseModel):
    provider: Literal["aws"] = "aws"
    capability: Capability
    state: Literal["not_configured", "configured_unverified", "invalid_configuration"]
    reason: Literal["role_binding_missing", "role_binding_invalid", "partition_unsupported"] | None
    provider_check: Literal["not_performed"] = "not_performed"
    provider_requests_performed: Literal[False] = False
    sample_available: bool


def connection_status(organization_id: str, capability: Capability) -> ConnectionStatus:
    organization_id = str(UUID(organization_id))
    config = settings()
    mapping = (
        config.aws_role_bindings if capability == "posture" else config.aws_billing_role_bindings
    )
    role = mapping.get(organization_id)
    state = "not_configured"
    reason: str | None = "role_binding_missing"
    if role is not None:
        try:
            identity = AWSAccountIdentity.from_role(role)
            if capability == "billing" and identity.partition != "aws":
                state, reason = "invalid_configuration", "partition_unsupported"
            else:
                state, reason = "configured_unverified", None
        except ValueError:
            state, reason = "invalid_configuration", "role_binding_invalid"
    return ConnectionStatus.model_validate(
        {
            "capability": capability,
            "state": state,
            "reason": reason,
            "sample_available": capability == "billing" and config.environment == "development",
        }
    )
