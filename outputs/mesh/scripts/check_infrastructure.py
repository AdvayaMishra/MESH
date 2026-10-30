"""Read-only application protocol checks. Never prints secrets or raw errors."""

import argparse
import json
import shutil
import smtplib
import socket
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
sys.path.insert(0, str(ROOT / "backend"))
from app.core.config import settings  # noqa: E402


def check():
    from app.core.db import assert_runtime_role
    from redis import Redis
    from sqlalchemy import create_engine, text
    from sqlalchemy.orm import Session

    config = settings()
    checks = {}
    docker = shutil.which("docker")
    if docker:
        try:
            result = subprocess.run(
                [docker, "version", "--format", "{{.Server.Version}}"],
                capture_output=True,
                timeout=15,
                check=False,
            )
            checks["docker_engine"] = (
                "passed" if result.returncode == 0 else "blocked: engine unavailable"
            )
        except (OSError, subprocess.TimeoutExpired):
            checks["docker_engine"] = "blocked: engine probe failed"
    else:
        checks["docker_engine"] = "blocked: Docker is not installed"
    engine = create_engine(config.database_url, connect_args={"connect_timeout": 5})
    try:
        with Session(engine) as db:
            assert_runtime_role(db)
            assert db.scalar(text("SELECT 1")) == 1
        checks["postgresql_restricted_runtime"] = "passed"
    except Exception:
        checks["postgresql_restricted_runtime"] = "blocked: connection or role validation failed"
    finally:
        engine.dispose()
    try:
        with Redis.from_url(config.redis_url, socket_connect_timeout=2, socket_timeout=2) as redis:
            assert redis.ping()
        checks["redis_ping"] = "passed"
    except Exception:
        checks["redis_ping"] = "blocked: Redis protocol check failed"
    if config.smtp_host:
        try:
            with smtplib.SMTP(config.smtp_host, config.smtp_port, timeout=3) as smtp:
                assert smtp.ehlo()[0] == 250
            checks["smtp_ehlo"] = (
                "passed: greeting only; delivery/authentication requires separate verification"
            )
        except (OSError, smtplib.SMTPException, AssertionError):
            checks["smtp_ehlo"] = "blocked: SMTP protocol check failed"
    else:
        checks["smtp_ehlo"] = "blocked: SMTP host is not configured"
    if config.clamav_host:
        try:
            with socket.create_connection(
                (config.clamav_host, config.clamav_port), timeout=3
            ) as connection:
                connection.sendall(b"zPING\0")
                assert connection.recv(64).strip(b"\0\r\n") == b"PONG"
            checks["clamav_ping"] = "passed: ping only; clean/EICAR scanning remains separate"
        except (OSError, AssertionError):
            checks["clamav_ping"] = "blocked: ClamAV protocol check failed"
    else:
        checks["clamav_ping"] = "blocked: ClamAV host is not configured"
    return {
        "verified_at_utc": datetime.now(UTC).isoformat(),
        "checks": checks,
        "ready": all(value.startswith("passed") for value in checks.values()),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = check()
    if args.output:
        args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    sys.exit(0 if report["ready"] else 1)
