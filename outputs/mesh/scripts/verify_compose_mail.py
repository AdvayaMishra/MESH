"""Resolve real Compose with isolated fixtures; never start services or load real secrets."""

import argparse
import hashlib
import json
import os
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def verify(command: list[str]) -> dict:
    environment = {
        key: value
        for key, value in os.environ.items()
        if key.upper() in {"PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "HOME"}
    }
    results = {}
    with tempfile.TemporaryDirectory(prefix="mesh-compose-mail-") as directory:
        for name, extra, expected in (
            ("mailpit_defaults", "", "1025"),
            (
                "external_authenticated_smtp",
                "SMTP_HOST=smtp.gmail.com\nSMTP_PORT=587\nSMTP_STARTTLS=true\nSMTP_USERNAME=fixture@example.invalid\nSMTP_PASSWORD=fixture-only-password\nCLAMAV_HOST=scanner.example.invalid\nCLAMAV_PORT=13310\nCLAMAV_TLS=true\nCLAMAV_CA_FILE=/run/mesh-fixture/ca.pem\nCLAMAV_TLS_SERVER_NAME=scanner.example.invalid\n",
                "587",
            ),
        ):
            fixture = Path(directory) / (name + ".env")
            fixture.write_text(
                "POSTGRES_ADMIN_PASSWORD=fixture-admin\nMESH_DB_PASSWORD=fixture-runtime\nAUTH_RATE_SECRET="
                + "a" * 48
                + "\n"
                + extra,
                encoding="utf-8",
            )
            response = subprocess.run(
                [
                    *command,
                    "--project-name",
                    "mesh-config-validation",
                    "--env-file",
                    str(fixture),
                    "--file",
                    str(ROOT / "docker-compose.yml"),
                    "--profile",
                    "*",
                    "config",
                    "--format",
                    "json",
                ],
                cwd=ROOT,
                env=environment,
                capture_output=True,
                timeout=30,
                check=True,
            )
            if len(response.stdout) > 2097152:
                raise ValueError("Compose output exceeds bounds")
            config = json.loads(response.stdout)
            services = {
                key: value
                for key, value in config["services"].items()
                if "SMTP_PORT" in value.get("environment", {})
            }
            if not {"api", "worker"}.issubset(services):
                raise ValueError("Runtime mail services missing")
            for service in services.values():
                values = service["environment"]
                if str(values["SMTP_PORT"]) != expected:
                    raise ValueError("Configured SMTP port was not propagated")
                if name == "external_authenticated_smtp" and (
                    values["SMTP_HOST"] != "smtp.gmail.com"
                    or str(values["SMTP_STARTTLS"]).lower() != "true"
                ):
                    raise ValueError("External secure mail transport was not propagated")
                if name == "external_authenticated_smtp" and (
                    str(values["CLAMAV_PORT"]) != "13310"
                    or str(values["CLAMAV_TLS"]).lower() != "true"
                    or values["CLAMAV_CA_FILE"] != "/run/mesh-fixture/ca.pem"
                    or values["CLAMAV_TLS_SERVER_NAME"] != "scanner.example.invalid"
                ):
                    raise ValueError("Verified malware TLS configuration was not propagated")
            results[name] = {
                "passed": True,
                "runtime_services_checked": sorted(services),
                "smtp_port": int(expected),
                "malware_tls_configuration_propagated": name == "external_authenticated_smtp",
            }
    return {
        "passed": True,
        "checks": results,
        "compose_sha256": hashlib.sha256((ROOT / "docker-compose.yml").read_bytes()).hexdigest(),
        "services_started": False,
        "real_runtime_env_loaded": False,
        "live_mail_delivery_verified": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    tool = parser.add_mutually_exclusive_group(required=True)
    tool.add_argument("--compose-executable", type=Path)
    tool.add_argument("--docker-executable", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if (
        args.output.resolve() == (ROOT / "docker-compose.yml").resolve()
        or args.output.suffix == ".env"
    ):
        print(json.dumps({"passed": False, "status": "refusing_configuration_overwrite"}))
        return 1
    try:
        executable = args.compose_executable or args.docker_executable
        if not executable.is_absolute() or not executable.is_file():
            raise ValueError("Absolute operator-trusted Compose/Docker executable required")
        report = verify([str(executable)] + (["compose"] if args.docker_executable else []))
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError):
        report = {
            "passed": False,
            "status": "compose_configuration_verification_failed",
            "services_started": False,
            "real_runtime_env_loaded": False,
        }
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
