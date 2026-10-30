"""Bounded reported telemetry metadata; never raw IPs, device dumps or arbitrary logs."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

EventCategory = Literal[
    "authentication",
    "session",
    "device",
    "api",
    "privilege",
    "database",
    "file",
    "download",
    "repository",
    "cloud",
    "cloud_audit",
    "network",
    "behavior",
]
SourceKind = Literal[
    "authentication",
    "session",
    "device",
    "api",
    "privilege",
    "database",
    "file",
    "repository",
    "cloud_configuration",
    "cloud_audit",
    "network",
    "manual",
]
EventSeverity = Literal["info", "low", "medium", "high", "critical"]
VolumeCategory = Literal[
    "api", "database", "download", "file", "network", "repository", "cloud_audit"
]
VOLUME_CATEGORIES = ("api", "database", "download", "file", "network", "repository", "cloud_audit")
Slug = Annotated[str, Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")]


class Metadata(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, hide_input_in_errors=True)


class PseudonymousDigest(Metadata):
    value: Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
    method: Literal["hmac-sha256"]
    key_id: Slug


class SourceMetadata(Metadata):
    kind: SourceKind
    name: Slug
    version: Annotated[str | None, Field(pattern=r"^[0-9]+(?:\.[0-9]+){0,3}$", max_length=20)] = (
        None
    )


class IPMetadata(Metadata):
    address: PseudonymousDigest | None = None
    country_code: Annotated[str | None, Field(pattern=r"^[A-Z]{2}$")] = None
    asn: Annotated[int | None, Field(strict=True, ge=1, le=4294967295)] = None


class DeviceMetadata(Metadata):
    fingerprint: PseudonymousDigest | None = None
    os_family: Literal["windows", "macos", "linux", "android", "ios", "other", "unknown"] | None = (
        None
    )
    new_device: Annotated[bool | None, Field(strict=True)] = None
    managed: Annotated[bool | None, Field(strict=True)] = None


class EventAttributes(Metadata):
    operation: Literal["read", "write", "delete", "execute", "configure"] | None = None
    data_classification: (
        Literal["public", "internal", "confidential", "restricted", "unknown"] | None
    ) = None
    bytes_transferred: Annotated[int | None, Field(strict=True, ge=0, le=10**15)] = None
    permissions_changed: Annotated[bool | None, Field(strict=True)] = None
    repository_action: (
        Literal["push", "pull", "membership", "branch_protection", "configuration"] | None
    ) = None
    cloud_service: Literal["s3", "iam", "ec2", "rds", "cloudtrail", "other"] | None = None


class EventContext(Metadata):
    source: SourceMetadata | None = None
    reported_severity: EventSeverity | None = None
    ip: IPMetadata | None = None
    device: DeviceMetadata | None = None
    attributes: EventAttributes | None = None
