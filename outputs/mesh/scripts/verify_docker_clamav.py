"""Opt-in isolated Compose ClamAV acceptance with signed operator-supplied databases.

Uses only generated project resources, synthetic bytes and a trusted backend probe
image. Never reads hosted .env or publishes a scanner port on the host.
"""

import argparse
import json
import re
import secrets
import subprocess
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from dotenv import dotenv_values
from verify_docker_runtime import disposable_environment

ROOT = Path(__file__).resolve().parents[1]

PROBE = """
import io,sys
from PIL import Image
from fastapi import HTTPException
from app.core.config import settings
from app.documents import malware_gate
settings().clamav_host='clamav'
settings().clamav_port=3310
if sys.argv[1]=='outage':
    try: malware_gate(b'clean synthetic bytes')
    except HTTPException as error: assert error.status_code==503
    else: raise AssertionError('Scanner outage must fail closed')
else:
    output=io.BytesIO()
    Image.new('RGB',(4,4),'white').save(output,'PNG')
    malware_gate(output.getvalue())
    eicar=b'X5O!P%@AP[4'+bytes([92])+b'PZX54(P^)7CC)7}$'+b'EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*'
    assert len(eicar)==68
    try: malware_gate(eicar)
    except HTTPException as error: assert error.status_code==422
    else: raise AssertionError('Standard EICAR fixture was not rejected')
"""


def verify(
    docker: Path,
    compose: Path,
    definitions: Path,
    workspace: Path,
    probe_image: str,
    dedicated: bool,
):
    if not dedicated or not all(
        path.is_absolute() for path in (docker, compose, definitions, workspace)
    ):
        raise ValueError("Absolute paths and dedicated disposable host opt-in required")
    if (
        not docker.is_file()
        or not compose.is_file()
        or not definitions.is_dir()
        or not workspace.is_dir()
    ):
        raise ValueError("Tools, signed database directory and workspace must exist")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_./:@-]{0,254}", probe_image):
        raise ValueError("Invalid trusted probe image reference")
    for name in ("main", "daily", "bytecode"):
        path = definitions / (name + ".cvd")
        if not path.is_file() or path.is_symlink():
            raise ValueError("Three ordinary signed CVD files required")
    project = "mesh-test-" + uuid4().hex[:12]
    checks, databases = {}, {}
    environment = disposable_environment(dict(dotenv_values(ROOT / ".env.example")))
    ledger = workspace / "clamav-runtime-fixtures.json"
    if ledger.exists():
        raise RuntimeError("Prior disposable ClamAV project requires scoped cleanup")
    image = next(
        line.split("image:", 1)[1].strip()
        for line in (ROOT / "docker-compose.yml").read_text().splitlines()
        if "image: clamav/clamav:" in line
    )
    assert re.fullmatch(r"clamav/clamav:[a-zA-Z0-9_.-]+@sha256:[a-f0-9]{64}", image)
    with tempfile.TemporaryDirectory(prefix="mesh-clamav-acceptance-", dir=workspace) as folder:
        work = Path(folder)
        assert work.resolve().is_relative_to(workspace.resolve())
        envfile = work / "compose.env"
        envfile.write_text(
            "POSTGRES_ADMIN_PASSWORD="
            + secrets.token_urlsafe(32)
            + "\nMESH_DB_PASSWORD="
            + secrets.token_urlsafe(32)
            + "\n"
        )
        override = work / "clamav.json"
        override.write_text(
            json.dumps(
                {
                    "services": {
                        "clamav": {
                            "environment": {
                                "CLAMAV_NO_FRESHCLAMD": "true",
                                "CLAMD_CONF_MaxThreads": "2",
                                "CLAMD_CONF_MaxQueue": "4",
                            }
                        }
                    }
                }
            )
        )
        base = [
            str(compose),
            "--project-directory",
            str(ROOT),
            "--env-file",
            str(envfile),
            "-p",
            project,
            "-f",
            str(ROOT / "docker-compose.yml"),
            "-f",
            str(override),
            "--profile",
            "documents",
        ]
        ledger.write_text(json.dumps({"project": project, "kind": "clamav-disposable-acceptance"}))

        def run(command, label, timeout=120):
            path = workspace / (project + "-clamav-" + label + ".log")
            with path.open("wb") as log:
                result = subprocess.run(
                    command,
                    cwd=ROOT,
                    env=environment,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    timeout=timeout,
                )
            if result.returncode:
                raise RuntimeError(label + " failed")
            return path.read_text(errors="replace").strip()

        stage = "create_pinned_compose_scanner"
        try:
            run(base + ["create", "--no-build", "clamav"], "create", 900)
            container = run(base + ["ps", "--all", "-q", "clamav"], "container", 30)
            assert re.fullmatch(r"[a-f0-9]{64}", container)
            for name in ("main", "daily", "bytecode"):
                run(
                    [
                        str(docker),
                        "cp",
                        str(definitions / (name + ".cvd")),
                        container + ":/var/lib/clamav/" + name + ".cvd",
                    ],
                    "copy_" + name,
                )
                output = run(
                    [
                        str(docker),
                        "run",
                        "--rm",
                        "--network=none",
                        "--read-only",
                        "--cap-drop=ALL",
                        "--security-opt=no-new-privileges",
                        "--mount",
                        f"type=volume,src={project}_clamav-signatures,dst=/var/lib/clamav,readonly",
                        "--entrypoint=sigtool",
                        image,
                        "--info=/var/lib/clamav/" + name + ".cvd",
                    ],
                    "signature_" + name,
                )
                assert "Verification OK." in output
                version = int(re.search(r"^Version: (\d+)$", output, re.M).group(1))
                built = datetime.strptime(
                    re.search(r"^Build time: (.+)$", output, re.M).group(1), "%d %b %Y %H:%M %z"
                )
                if name == "daily":
                    assert 0 <= (datetime.now(UTC) - built).total_seconds() <= 72 * 3600
                databases[name] = {
                    "version": version,
                    "built_at_utc": built.astimezone(UTC).isoformat(),
                    "digital_signature_verified": True,
                }
            checks["pinned_compose_image_and_three_signed_databases"] = "passed"
            stage = "actual_clamd_health"
            run(base + ["start", "clamav"], "start")
            deadline = time.monotonic() + 600
            while time.monotonic() < deadline:
                state = json.loads(
                    run(
                        [str(docker), "inspect", "--format", "{{json .State}}", container],
                        "health",
                        30,
                    )
                )
                if state.get("Health", {}).get("Status") == "healthy":
                    break
                if not state["Running"]:
                    raise RuntimeError("ClamAV stopped before becoming healthy")
                time.sleep(3)
            else:
                raise TimeoutError("ClamAV health deadline")
            checks["actual_compose_clamd_healthy"] = "passed"
            probe = [
                str(docker),
                "run",
                "--rm",
                "--network",
                project + "_default",
                "--read-only",
                "--user=10001:10001",
                "--cap-drop=ALL",
                "--security-opt=no-new-privileges",
                "--pids-limit=32",
                "--memory=256m",
                "--memory-swap=256m",
                "--entrypoint=python",
                probe_image,
                "-c",
                PROBE,
            ]
            stage = "actual_clean_png_and_eicar_upload_gate"
            run(probe + ["scan"], "upload_gate")
            checks[stage] = "passed"
            run(base + ["stop", "clamav"], "stop")
            stage = "actual_engine_outage_fails_closed"
            run(probe + ["outage"], "outage")
            checks[stage] = "passed"
        except Exception as error:
            checks[stage] = "failed: " + type(error).__name__
        finally:
            try:
                run(base + ["down", "--volumes", "--remove-orphans"], "cleanup", 180)
                checks["own_project_container_network_and_volume_removed"] = "passed"
                ledger.unlink()
            except Exception as error:
                checks["cleanup"] = "failed: " + type(error).__name__
    return {
        "verified_at_utc": datetime.now(UTC).isoformat(),
        "checks": checks,
        "passed": all(value == "passed" for value in checks.values()),
        "databases": databases,
        "image": image,
        "limitations": [
            "Only generated Compose resources and synthetic PNG/EICAR bytes. No identity document or hosted credential is used.",
            "Current operator-supplied CVDs are digitally verified inside the Linux image. FreshClam is disabled for this bounded offline-definition test; ongoing production updating remains separate.",
            "Test override bounds ClamAV to two scan threads and four queued requests; no host scanner port is published.",
        ],
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--docker-executable", type=Path, required=True)
    parser.add_argument("--compose-executable", type=Path, required=True)
    parser.add_argument("--definitions", type=Path, required=True)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--probe-image", default="mesh-backend:local")
    parser.add_argument("--dedicated-disposable-docker-host", action="store_true")
    args = parser.parse_args()
    report = verify(
        args.docker_executable,
        args.compose_executable,
        args.definitions,
        args.workspace,
        args.probe_image,
        args.dedicated_disposable_docker_host,
    )
    (ROOT / "docs/clamav-container-results.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    raise SystemExit(0 if report["passed"] else 1)
