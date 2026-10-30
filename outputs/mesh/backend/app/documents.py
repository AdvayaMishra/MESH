import hashlib
import io
import json
import socket
import ssl
import struct
import warnings
from contextlib import nullcontext
from datetime import UTC, datetime, timedelta
from time import monotonic
from typing import Any
from urllib.parse import parse_qs, urlsplit
from uuid import UUID

import httpx
from fastapi import HTTPException
from PIL import Image
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import Principal
from app.core.config import settings
from app.document_authority import upload_authority
from app.models import DocumentHold, IdentityDocument, Organization, identifier, now
from app.services import emit, lock_tenant

Image.MAX_IMAGE_PIXELS = 10000000


def private_key(key: str) -> str:
    try:
        parts = key.split("/")
        if len(parts) != 3 or any(str(UUID(part)) != part for part in parts):
            raise ValueError("Noncanonical object key")
    except (ValueError, AttributeError, TypeError):
        raise HTTPException(503, "Invalid private object reference") from None
    return key


def document_key(record: IdentityDocument, organization_id: str) -> str:
    key = private_key(record.storage_key)
    if (
        record.organization_id != organization_id
        or key != f"{record.organization_id}/{record.employee_id}/{record.id}"
    ):
        raise HTTPException(503, "Invalid private object reference")
    return key


def validate_image(content: bytes, media_type: str) -> None:
    if not content or len(content) > 2 * 1024 * 1024:
        raise HTTPException(422, "Identity image must be at most 2 MiB")
    signatures = {"image/png": b"\x89PNG\r\n\x1a\n", "image/jpeg": b"\xff\xd8\xff"}
    if media_type not in signatures or not content.startswith(signatures[media_type]):
        raise HTTPException(422, "Only validated PNG/JPEG identity images are accepted")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(content)) as image:
                if image.format not in {"PNG", "JPEG"} or image.width * image.height > 10000000:
                    raise ValueError("Image exceeds dimensions")
                image.verify()
    except (
        OSError,
        ValueError,
        SyntaxError,
        EOFError,
        struct.error,
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
    ):
        raise HTTPException(422, "Invalid or oversized identity image") from None


def clamav_verdict(response: bytes) -> None:
    # The zINSTREAM command requires a NUL-terminated response. A truncated
    # clean-looking response or engine error must never clear an upload.
    if not response.endswith(b"\0") or len(response) > 4096 or b"\0" in response[:-1]:
        raise HTTPException(503, "Malware scanner returned an invalid response")
    verdict = response[:-1]
    if verdict == b"stream: OK":
        return
    if verdict.startswith(b"stream: ") and verdict.endswith(b" FOUND"):
        raise HTTPException(422, "Identity image was not cleared by malware screening")
    raise HTTPException(503, "Malware scanner could not complete analysis")


def malware_gate(content: bytes) -> None:
    config = settings()
    if not config.clamav_host:
        raise HTTPException(503, "Malware scanning must be configured before upload")
    deadline = monotonic() + 20

    def remaining():
        value = deadline - monotonic()
        if value <= 0:
            raise TimeoutError("Malware screening exceeded its deadline")
        return min(10, value)

    try:
        context = (
            ssl.create_default_context(cafile=config.clamav_ca_file or None)
            if config.clamav_tls
            else None
        )
        with socket.create_connection(
            (config.clamav_host, config.clamav_port), timeout=remaining()
        ) as raw:
            raw.settimeout(remaining())
            secured = (
                context.wrap_socket(
                    raw, server_hostname=config.clamav_tls_server_name or config.clamav_host
                )
                if context
                else nullcontext(raw)
            )
            with secured as connection:
                connection.settimeout(remaining())
                connection.sendall(b"zINSTREAM\0")
                for start in range(0, len(content), 65536):
                    connection.settimeout(remaining())
                    chunk = content[start : start + 65536]
                    connection.sendall(struct.pack("!I", len(chunk)) + chunk)
                connection.settimeout(remaining())
                connection.sendall(struct.pack("!I", 0))
                result = bytearray()
                while len(result) < 4096:
                    connection.settimeout(remaining())
                    chunk = connection.recv(1024)
                    if not chunk:
                        break
                    result.extend(chunk)
                    if b"\0" in result:
                        break
                clamav_verdict(bytes(result))
    except (OSError, ValueError):
        raise HTTPException(503, "Malware scanner unavailable") from None


class PrivateStorage:
    def __init__(self, client: httpx.Client | None = None):
        self.client = client

    def request(self, method: str, path: str, **kwargs) -> Any:
        binary = kwargs.pop("binary", False)
        config = settings()
        if not config.supabase_url or not config.supabase_storage_key:
            raise HTTPException(503, "Private Storage is not configured")
        key = config.supabase_storage_key.get_secret_value()
        if key.startswith("sb_publishable_"):
            raise HTTPException(503, "Private Storage requires a backend secret key")
        headers = {
            name: value
            for name, value in kwargs.pop("headers", {}).items()
            if name.lower() not in {"apikey", "authorization", "accept-encoding"}
        }
        headers["apikey"] = key
        headers["Accept-Encoding"] = "identity"
        deadline = monotonic() + 20
        # Opaque sb_secret keys are API keys, not JWTs. Legacy service-role JWTs
        # still use Bearer auth; never send a new secret key as a bearer token.
        if not key.startswith("sb_secret_"):
            headers["Authorization"] = "Bearer " + key

        def receive(client: httpx.Client):
            if monotonic() >= deadline:
                raise ValueError("Storage dispatch exceeded time bound")
            with client.stream(
                method,
                config.supabase_url.rstrip("/") + "/storage/v1/" + path,
                headers=headers,
                follow_redirects=False,
                timeout=15,
                **kwargs,
            ) as response:
                response.raise_for_status()
                allowed = (
                    {200} if method == "GET" else {200, 204} if method == "DELETE" else {200, 201}
                )
                length = response.headers.get("content-length")
                if (
                    response.status_code not in allowed
                    or response.headers.get("content-encoding", "identity").strip().lower()
                    != "identity"
                    or monotonic() >= deadline
                    or (
                        length is not None
                        and (
                            len(length) > 10
                            or not length.isascii()
                            or not length.isdecimal()
                            or int(length) > 2 * 1024 * 1024
                        )
                    )
                ):
                    raise ValueError("Storage response metadata or time bound exceeded")
                content = bytearray()
                for chunk in response.iter_bytes():
                    if monotonic() >= deadline or len(content) + len(chunk) > 2 * 1024 * 1024:
                        raise ValueError("Storage response exceeded bound")
                    content.extend(chunk)
                if monotonic() >= deadline or (length is not None and len(content) != int(length)):
                    raise ValueError("Storage response time or declared size mismatch")
                result = bytes(content) if binary else json.loads(content) if content else {}
                if monotonic() >= deadline:
                    raise ValueError("Storage response decoding exceeded time bound")
                return result

        try:
            if self.client:
                return receive(self.client)
            with httpx.Client(timeout=15, follow_redirects=False) as client:
                return receive(client)
        except (httpx.HTTPError, ValueError, RecursionError):
            raise HTTPException(503, "Private Storage operation failed") from None

    def upload(self, key: str, content: bytes, media_type: str) -> None:
        key = private_key(key)
        self.request(
            "POST",
            "object/mesh-identity/" + key,
            content=content,
            headers={"Content-Type": media_type, "x-upsert": "false"},
        )

    def download(self, key: str) -> bytes:
        key = private_key(key)
        return self.request("GET", "object/authenticated/mesh-identity/" + key, binary=True)

    def sign(self, key: str) -> str:
        key = private_key(key)
        result = self.request("POST", "object/sign/mesh-identity/" + key, json={"expiresIn": 60})
        signed = result.get("signedURL", "") if isinstance(result, dict) else ""
        if not isinstance(signed, str) or len(signed) > 16384:
            raise HTTPException(503, "Unexpected private Storage response")
        try:
            parts = urlsplit(signed)
        except ValueError:
            raise HTTPException(503, "Unexpected private Storage response") from None
        if (
            parts.scheme
            or parts.netloc
            or parts.fragment
            or parts.path != "/object/sign/mesh-identity/" + key
            or not parse_qs(parts.query).get("token")
        ):
            raise HTTPException(503, "Unexpected private Storage response")
        return settings().supabase_url.rstrip("/") + "/storage/v1" + signed

    def delete(self, key: str) -> None:
        key = private_key(key)
        self.request("DELETE", "object/mesh-identity", json={"prefixes": [key]})

    def list(self, prefix: str, offset: int = 0) -> list[dict]:
        result = self.request(
            "POST",
            "object/list/mesh-identity",
            json={
                "prefix": prefix,
                "limit": 100,
                "offset": offset,
                "sortBy": {"column": "name", "order": "asc"},
            },
        )
        if (
            not isinstance(result, list)
            or len(result) > 100
            or any(not isinstance(row, dict) for row in result)
        ):
            raise HTTPException(503, "Invalid private Storage inventory")
        return result


def store(
    db: Session, p: Principal, employee_id: str, media_type: str, content: bytes
) -> IdentityDocument:
    if (
        len(content) > 2097152
        or not content
        or media_type not in {"image/png", "image/jpeg"}
        or not content.startswith(
            b"\x89PNG\r\n\x1a\n" if media_type == "image/png" else b"\xff\xd8\xff"
        )
    ):
        raise HTTPException(422, "Only bounded PNG/JPEG identity images are accepted")
    malware_gate(content)
    validate_image(content, media_type)
    upload_authority(db, p, employee_id)
    # Serialize upload/commit against orphan reconciliation for this tenant.
    db.scalar(
        select(Organization)
        .where(Organization.id == p.organization_id)
        .with_for_update(key_share=True)
    )
    record = IdentityDocument(
        id=identifier(),
        organization_id=p.organization_id,
        employee_id=employee_id,
        storage_key="",
        media_type=media_type,
        digest=hashlib.sha256(content).hexdigest(),
        expires_at=now() + timedelta(days=30),
        ocr_status="queued" if settings().document_ocr_enabled else "not_configured",
    )
    record.storage_key = f"{p.organization_id}/{employee_id}/{record.id}"
    # Stage the reference before external upload. On transaction failure, the
    # tenant-scoped reconciler can remove an old orphan after the grace period.
    db.add(record)
    db.flush()
    PrivateStorage().upload(record.storage_key, content, media_type)
    emit(db, p, "employee.document.uploaded", record.id)
    return record


def expire(db: Session, p: Principal) -> int:
    lock_tenant(db, p.organization_id)
    rows = db.scalars(
        select(IdentityDocument)
        .where(
            IdentityDocument.organization_id == p.organization_id,
            IdentityDocument.expires_at <= now(),
            IdentityDocument.status != "deleted",
            ~select(DocumentHold.id)
            .where(
                DocumentHold.organization_id == IdentityDocument.organization_id,
                DocumentHold.document_id == IdentityDocument.id,
                DocumentHold.released_at.is_(None),
            )
            .exists(),
        )
        .order_by(IdentityDocument.expires_at, IdentityDocument.id)
        .limit(50)
        .with_for_update(skip_locked=True)
    ).all()
    for record in rows:
        PrivateStorage().delete(document_key(record, p.organization_id))
        record.status = "deleted"
        record.ocr_status, record.ocr_ciphertext, record.ocr_lease_until = "cancelled", None, None
        emit(db, p, "employee.document.expired", record.id)
    return len(rows)


def reconcile_orphans(
    db: Session,
    p: Principal,
    *,
    grace_hours: int = 24,
    apply: bool = False,
    storage: PrivateStorage | None = None,
) -> dict[str, int]:
    """Inventory only this tenant's UUID paths; delete old unreferenced files explicitly.

    The same organization lock is held by uploads through their DB commit. Never
    delete if inventory is incomplete; never infer age from an untrusted filename.
    """
    if grace_hours < 24:
        raise HTTPException(422, "Orphan grace must be at least 24 hours")
    organization = db.scalar(
        select(Organization)
        .where(Organization.id == p.organization_id)
        .with_for_update(key_share=True)
    )
    if organization is None:
        raise HTTPException(404, "Retention organization not found")
    storage = storage or PrivateStorage()
    references = set(
        db.scalars(
            select(IdentityDocument.storage_key).where(
                IdentityDocument.organization_id == p.organization_id
            )
        ).all()
    )
    cutoff = now() - timedelta(hours=grace_hours)
    seen = 0
    candidates: list[str] = []

    def inventory(prefix):
        nonlocal seen
        for offset in range(0, 10001, 100):
            page = storage.list(prefix, offset)
            seen += len(page)
            if seen > 10000:
                raise HTTPException(503, "Storage inventory exceeds reconciliation bound")
            yield from page
            if len(page) < 100:
                return
        raise HTTPException(503, "Storage inventory pagination exceeded bound")

    for folder in inventory(p.organization_id + "/"):
        try:
            employee = str(UUID(folder["name"]))
        except (ValueError, KeyError, TypeError, AttributeError):
            continue
        if folder.get("id") is not None or folder["name"] != employee:
            continue
        for entry in inventory(f"{p.organization_id}/{employee}/"):
            try:
                name = str(UUID(entry["name"]))
                if name != entry["name"] or not entry.get("id"):
                    continue
                timestamps = [
                    datetime.fromisoformat(entry[key].replace("Z", "+00:00"))
                    for key in ("created_at", "updated_at")
                ]
                if any(value.tzinfo is None for value in timestamps):
                    continue
                if max(value.astimezone(UTC) for value in timestamps) >= cutoff:
                    continue
            except (ValueError, KeyError, TypeError, AttributeError):
                continue
            key = f"{p.organization_id}/{employee}/{name}"
            if key not in references:
                candidates.append(key)
    removed = 0
    if apply:
        for key in list(dict.fromkeys(candidates))[:50]:
            storage.delete(key)
            removed += 1
        if removed:
            emit(db, p, "employee.document.orphans_removed", p.organization_id)
    return {"inventoried": seen, "candidates": len(set(candidates)), "removed": removed}
