"""Negative configuration test: exported application secrets cannot enter test Compose."""

import argparse
import json
import os
import subprocess
import tempfile
from pathlib import Path

from dotenv import dotenv_values
from verify_docker_runtime import disposable_environment

ROOT = Path(__file__).resolve().parents[1]


def verify(compose: Path, workspace: Path):
    if (
        not compose.is_absolute()
        or not compose.is_file()
        or not workspace.is_absolute()
        or not workspace.is_dir()
    ):
        raise ValueError("Absolute Compose executable and workspace directory required")
    config = {
        key: value
        for key, value in dotenv_values(ROOT / ".env.example").items()
        if value is not None
    }
    config.update(
        {
            "POSTGRES_ADMIN_PASSWORD": "synthetic_admin_configuration_only",
            "MESH_DB_PASSWORD": "synthetic_runtime_configuration_only",
            "AUTH_RATE_SECRET": "d" * 48,
            "SUPABASE_URL": "https://identity.mesh.invalid",
            "SUPABASE_STORAGE_KEY": "",
        }
    )
    poisoned = {
        **os.environ,
        "DATABASE_URL": "forbidden-sentinel-database",
        "SUPABASE_URL": "https://forbidden-sentinel.invalid",
        "SUPABASE_STORAGE_KEY": "forbidden-sentinel-storage",
        "AUTH_RATE_SECRET": "forbidden-sentinel-limiter",
        "GITHUB_PRIVATE_KEY": "forbidden-sentinel-private-key",
        "COMPOSE_PROFILES": "forbidden-sentinel-profile",
    }
    environment = disposable_environment(config, poisoned)
    assert all(key not in environment for key in config)
    assert "COMPOSE_PROFILES" not in environment
    for key in ("DOCKER_HOST", "DOCKER_TLS_VERIFY", "DOCKER_CERT_PATH", "DOCKER_CONFIG"):
        assert environment.get(key) == poisoned.get(key)
    with tempfile.TemporaryDirectory(prefix="mesh-environment-test-", dir=workspace) as folder:
        target = Path(folder)
        assert target.resolve().is_relative_to(workspace.resolve())
        envfile = target / "generated.env"
        envfile.write_text("\n".join(key + "=" + value for key, value in config.items()) + "\n")
        output = subprocess.run(
            [
                str(compose),
                "--project-directory",
                str(ROOT),
                "--env-file",
                str(envfile),
                "-f",
                str(ROOT / "docker-compose.yml"),
                "--profile",
                "*",
                "config",
                "--format",
                "json",
            ],
            env=environment,
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=30,
            check=True,
        ).stdout
        assert "forbidden-sentinel" not in output
        runtime = json.loads(output)["services"]["api"]["environment"]
        assert runtime["SUPABASE_URL"] == config["SUPABASE_URL"]
        assert runtime["SUPABASE_STORAGE_KEY"] == ""
        assert runtime["AUTH_RATE_SECRET"] == config["AUTH_RATE_SECRET"]
        assert config["MESH_DB_PASSWORD"] in runtime["DATABASE_URL"]
    return {
        "passed": True,
        "checks": {
            "exported_backend_settings_removed": "passed",
            "compose_profile_controls_reset": "passed",
            "docker_connection_settings_preserved": "passed",
            "actual_compose_config_uses_generated_values": "passed",
        },
        "limitations": [
            "Configuration-only negative test; no Docker engine calls, containers or hosted credentials are used."
        ],
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compose-executable", type=Path, required=True)
    parser.add_argument("--workspace", type=Path, required=True)
    args = parser.parse_args()
    report = verify(args.compose_executable, args.workspace)
    (ROOT / "docs/verification-environment-results.json").write_text(
        json.dumps(report, indent=2) + "\n"
    )
    print(json.dumps(report, indent=2))
