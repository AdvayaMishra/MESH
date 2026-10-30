"""Opt-in scanner janitor acceptance using synthetic resources on a dedicated host."""

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.scan_janitor import sweep  # noqa: E402


def verify(docker: Path, image: str, dedicated: bool) -> dict:
    if not dedicated or not docker.is_absolute() or not docker.is_file():
        raise ValueError("Absolute Docker executable and dedicated disposable host required")
    if not image or image.startswith("-"):
        raise ValueError("Invalid local image reference")
    checks = {}
    container = "mesh-keeper-" + uuid4().hex
    volumes = ["mesh-" + str(uuid4()) for _ in range(3)]
    created = []

    def run(arguments):
        result = subprocess.run(
            [str(docker), *arguments], capture_output=True, text=True, timeout=45, check=True
        )
        if len(result.stdout) > 8 * 1024 * 1024:
            raise RuntimeError("Docker response exceeded bound")
        return result.stdout

    def labels(kind, *, recent=False, owned=True):
        values = {
            "mesh.managed-by": "mesh-scanner" if owned else "recovery-test-unowned",
            "mesh.temporary": "true",
            "mesh.resource": kind,
            "mesh.created-at": str(int(time.time()) - (0 if recent else 9000)),
        }
        return [arg for key, value in values.items() for arg in ("--label", key + "=" + value)]

    # Limit discovery to this verifier's resources, while the production janitor
    # still performs its actual Docker inspections, ownership/age checks and removals.
    def scoped_runner(arguments):
        output = run(arguments)
        if arguments[1] == "ls":
            allowed = set(volumes if arguments[0] == "volume" else [container_id[:12]])
            return "\n".join(line for line in output.splitlines() if line in allowed)
        return output

    try:
        for index, volume in enumerate(volumes):
            run(
                ["volume", "create", *labels("source", recent=index == 1, owned=index != 2), volume]
            )
            created.append(("volume", volume))
        container_id = run(
            [
                "create",
                "--name",
                container,
                *labels("scan"),
                "--network=none",
                "--read-only",
                "--user=10001:10001",
                "--cap-drop=ALL",
                "--security-opt=no-new-privileges",
                "--mount",
                f"type=volume,src={volumes[0]},dst=/repo,readonly",
                "--entrypoint=python",
                image,
                "-c",
                "pass",
            ]
        ).strip()
        created.append(("container", container))
        preview = sweep(runner=scoped_runner)
        assert preview == {"mode": "dry_run", "eligible": 2, "removed": 0, "failed": 0}
        run(["container", "inspect", container])
        run(["volume", "inspect", volumes[0]])
        checks["dry_run_preserves_stale_container_and_volume"] = "passed"
        applied = sweep(apply=True, runner=scoped_runner)
        assert applied == {"mode": "apply", "eligible": 2, "removed": 2, "failed": 0}
        checks["apply_removes_only_stale_owned_container_then_volume"] = "passed"
        for volume in volumes[1:]:
            run(["volume", "inspect", volume])
        checks["recent_and_unowned_volumes_preserved"] = "passed"
        assert sweep(apply=True, runner=scoped_runner)["removed"] == 0
        checks["repeat_is_idempotent"] = "passed"
    except Exception as error:
        checks["acceptance"] = "failed: " + type(error).__name__
    finally:
        for kind, name in reversed(created):
            subprocess.run(
                [str(docker), kind, "rm", "--force", name],
                capture_output=True,
                timeout=45,
                check=False,
            )
        try:
            remaining_volumes = set(run(["volume", "ls", "--format", "{{.Name}}"]).splitlines())
            remaining_containers = set(
                run(["container", "ls", "--all", "--format", "{{.Names}}"]).splitlines()
            )
            assert not remaining_volumes.intersection(volumes)
            assert container not in remaining_containers
            checks["synthetic_resources_removed"] = "passed"
        except Exception as error:
            checks["synthetic_resources_removed"] = "failed: " + type(error).__name__
    return {
        "checks": checks,
        "passed": bool(checks) and all(value == "passed" for value in checks.values()),
        "limitations": [
            "Synthetic labeled resource ages; does not crash the host or a production worker.",
            "Discovery is scoped to this verifier's resources; production ownership/age and deletion logic runs unchanged.",
        ],
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--docker-executable", type=Path, required=True)
    parser.add_argument("--image", default="mesh-scanner:local")
    parser.add_argument("--dedicated-disposable-docker-host", action="store_true")
    args = parser.parse_args()
    report = verify(args.docker_executable, args.image, args.dedicated_disposable_docker_host)
    (ROOT / "docs/scanner-recovery-live-results.json").write_text(
        json.dumps(report, indent=2) + "\n"
    )
    print(json.dumps(report, indent=2))
    raise SystemExit(0 if report["passed"] else 1)
