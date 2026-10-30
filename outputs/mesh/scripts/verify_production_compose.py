"""Offline real-Compose verification of the backend deployment scaffold."""

import argparse
import hashlib
import json
import os
import subprocess
import tempfile
from pathlib import Path

from cryptography.fernet import Fernet

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "infrastructure/deployment/compose.yml"


def verify(command: list[str]) -> dict:
    environment = {
        key: value
        for key, value in os.environ.items()
        if key.upper() in {"PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "HOME"}
    }
    with tempfile.TemporaryDirectory(prefix="mesh-production-config-") as directory:
        fixture = Path(directory) / "fixture.env"
        base = [
            *command,
            "--project-name",
            "mesh-production-config",
            "--env-file",
            str(fixture),
            "--file",
            str(MANIFEST),
            "--profile",
            "*",
            "config",
            "--format",
            "json",
        ]
        fixture.write_text("", encoding="utf-8")
        missing = subprocess.run(base, cwd=ROOT, env=environment, capture_output=True, timeout=30)
        if missing.returncode == 0:
            raise ValueError("Missing deployment secrets did not reject configuration")
        values = {
            "MESH_BACKEND_IMAGE": "registry.example.invalid/mesh-backend@sha256:" + "a" * 64,
            "MESH_TRUSTED_PROXY_IPS": "127.0.0.1",
            "DATABASE_URL": "postgresql+psycopg://runtime:fixture@database.example.invalid/mesh?sslmode=verify-full&sslrootcert=system",
            "REDIS_URL": "rediss://default:fixture@redis.example.invalid:6380/0",
            "AUTH_RATE_SECRET": "a" * 48,
            "SUPABASE_URL": "https://identity.example.invalid",
            "SUPABASE_ANON_KEY": "fixture-public-key",
            "CORS_ORIGINS": '["https://app.example.invalid"]',
            "INVITATION_BASE_URL": "https://app.example.invalid/invitations/accept",
            "SMTP_HOST": "smtp.example.invalid",
            "SMTP_PORT": "587",
            "SMTP_FROM": "fixture@example.invalid",
            "SMTP_USERNAME": "fixture@example.invalid",
            "SMTP_PASSWORD": "fixture-only-password",
            "MAIL_ENCRYPTION_KEY": Fernet.generate_key().decode(),
            "WORKER_ORGANIZATION_ID": "11111111-1111-4111-8111-111111111111",
            # Manifest-enforced production controls must override these inputs.
            "ENVIRONMENT": "development",
            "TEST_MODE": "true",
            "REQUIRE_PRIVILEGED_MFA": "false",
            "SMTP_STARTTLS": "false",
        }
        fixture.write_text(
            "\n".join(key + "=" + value for key, value in values.items()) + "\n", encoding="utf-8"
        )
        result = subprocess.run(
            base, cwd=ROOT, env=environment, capture_output=True, timeout=30, check=True
        )
        if len(result.stdout) > 2097152:
            raise ValueError("Resolved deployment manifest exceeded bounds")
        services = json.loads(result.stdout)["services"]
        if set(services) != {"api", "worker", "retention", "cloud-worker", "billing-worker"}:
            raise ValueError("Unexpected deployment service set")
        for name, service in services.items():
            if service["image"] != values["MESH_BACKEND_IMAGE"] or service.get("build"):
                raise ValueError("Deployment must use only the supplied immutable image")
            if (
                service.get("user") != "10001:10001"
                or service.get("read_only") is not True
                or "ALL" not in service.get("cap_drop", [])
                or "no-new-privileges:true" not in service.get("security_opt", [])
            ):
                raise ValueError("Required runtime restriction missing")
            if (
                service.get("volumes")
                or not service.get("healthcheck")
                or service.get("pids_limit") != 128
            ):
                raise ValueError("Unexpected mounts or missing supervision bounds")
            runtime = service["environment"]
            if (
                runtime["ENVIRONMENT"] != "production"
                or str(runtime["TEST_MODE"]).lower() != "false"
                or str(runtime["REQUIRE_PRIVILEGED_MFA"]).lower() != "true"
                or str(runtime["SMTP_STARTTLS"]).lower() != "true"
                or str(runtime["SMTP_PORT"]) != "587"
            ):
                raise ValueError("Production security/mail settings were weakened")
            if name != "api" and service.get("ports"):
                raise ValueError("Worker port must not be published")
        if {entry.get("host_ip") for entry in services["api"]["ports"]} != {"127.0.0.1"}:
            raise ValueError("API must remain behind the selected TLS ingress")
        if services["api"]["command"][-1] != values["MESH_TRUSTED_PROXY_IPS"]:
            raise ValueError("Exact proxy trust not propagated")
    return {
        "passed": True,
        "checks": {
            "missing_inputs_rejected": True,
            "immutable_image_and_no_build": True,
            "all_services_nonroot_readonly_restricted": True,
            "worker_ports_and_host_mounts_absent": True,
            "privileged_mfa_and_starttls_cannot_be_disabled_by_env": True,
            "smtp_port_587_propagated": True,
            "api_loopback_and_exact_proxy_trust": True,
            "worker_healthchecks_and_pid_bounds": True,
        },
        "services_checked": sorted(services),
        "manifest_sha256": hashlib.sha256(MANIFEST.read_bytes()).hexdigest(),
        "services_started": False,
        "real_credentials_loaded": False,
        "production_deployment_verified": False,
        "production_clearance": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    tool = parser.add_mutually_exclusive_group(required=True)
    tool.add_argument("--compose-executable", type=Path)
    tool.add_argument("--docker-executable", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.resolve() == MANIFEST.resolve() or args.output.suffix == ".env":
        print(json.dumps({"passed": False, "status": "refusing_configuration_overwrite"}))
        return 1
    try:
        executable = args.compose_executable or args.docker_executable
        if not executable.is_absolute() or not executable.is_file():
            raise ValueError("Absolute operator-trusted executable required")
        report = verify([str(executable)] + (["compose"] if args.docker_executable else []))
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError):
        report = {
            "passed": False,
            "status": "production_manifest_verification_failed",
            "services_started": False,
            "production_clearance": False,
        }
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
