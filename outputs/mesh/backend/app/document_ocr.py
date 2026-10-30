"""Bounded isolated OCR transport and encrypted, explicitly untrusted suggestions."""

import json

from cryptography.fernet import Fernet, InvalidToken
from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field

from app.core.config import settings
from app.core.time import as_utc
from app.models import IdentityDocument, now
from app.scanning import DockerSandbox, resource_labels


class Suggestions(BaseModel):
    model_config = ConfigDict(extra="forbid")
    suggested_name: str | None = Field(default=None, max_length=100)
    suggested_employee_id: str | None = Field(default=None, max_length=50)
    engine: str = Field(max_length=100)
    untrusted: bool = True


def cipher() -> Fernet:
    key = settings().document_ocr_key
    try:
        return Fernet(key.get_secret_value() if key else b"")
    except (ValueError, TypeError):
        raise HTTPException(503, "Private OCR encryption is not configured") from None


def encrypt(document: IdentityDocument, value: Suggestions) -> str:
    payload = {
        "document_id": document.id,
        "organization_id": document.organization_id,
        "suggestions": value.model_dump(),
    }
    return cipher().encrypt(json.dumps(payload).encode()).decode()


def decrypt(document: IdentityDocument) -> Suggestions | None:
    if not document.ocr_ciphertext:
        return None
    try:
        value = json.loads(cipher().decrypt(document.ocr_ciphertext.encode()))
        if (
            value["document_id"] != document.id
            or value["organization_id"] != document.organization_id
        ):
            raise ValueError("Wrong ciphertext context")
        return Suggestions.model_validate(value["suggestions"])
    except (InvalidToken, ValueError, KeyError, TypeError):
        raise HTTPException(503, "Private OCR result unavailable") from None


def pending(document: IdentityDocument) -> None:
    if document.status != "pending_hr" or as_utc(document.expires_at) <= now():
        raise HTTPException(409, "An unexpired pending identity document is required")


class OCRSandbox(DockerSandbox):
    def __init__(self):
        super().__init__(settings().document_ocr_image, timeout=60, max_output=8192)

    def command(self, name: str, volume: str, scanner: str) -> list[str]:
        if volume != "stdin" or scanner != "ocr":
            raise ValueError("Invalid OCR operation")
        return [
            settings().docker_executable,
            "run",
            "--name",
            name,
            *resource_labels("scan"),
            "--rm",
            "--pull=never",
            "--interactive",
            "--log-driver=none",
            "--network=none",
            "--read-only",
            "--cap-drop=ALL",
            "--security-opt=no-new-privileges",
            "--pids-limit=64",
            "--memory=512m",
            "--memory-swap=512m",
            "--cpus=1",
            "--ulimit=nofile=128:128",
            "--user=10001:10001",
            *[
                argument
                for proxy in (
                    "HTTP_PROXY",
                    "HTTPS_PROXY",
                    "FTP_PROXY",
                    "ALL_PROXY",
                    "NO_PROXY",
                    "http_proxy",
                    "https_proxy",
                    "ftp_proxy",
                    "all_proxy",
                    "no_proxy",
                )
                for argument in ("--env", proxy + "=")
            ],
            "--tmpfs=/tmp:rw,noexec,nosuid,size=64m",
            self.image,
        ]

    def analyze(self, content: bytes) -> Suggestions:
        result = Suggestions.model_validate(self.execute("stdin", "ocr", content))
        if result.untrusted is not True:
            raise ValueError("OCR suggestions must remain untrusted")
        return result
