"""Explicit cleanup on a dedicated Docker host; never broad Docker prune."""

import argparse
import json
import re
import subprocess  # nosec B404 # fixed Docker operations on the dedicated scanner host
import time
from typing import TypedDict

from app.core.config import settings


class SweepReport(TypedDict):
    mode: str
    eligible: int
    removed: int
    failed: int


def docker(arguments: list[str]) -> str:
    result = subprocess.run(  # nosec B603 # fixed Docker binary, allowlisted operations and verified resource names
        [settings().docker_executable, *arguments],
        capture_output=True,
        timeout=30,
        check=True,
    )
    if len(result.stdout) > 8 * 1024 * 1024:
        raise RuntimeError("Docker inventory exceeded bound")
    return result.stdout.decode("utf-8")


def eligible(kind: str, name: str, labels: dict, timestamp: float, minimum_age: int) -> bool:
    if labels.get("mesh.managed-by") != "mesh-scanner" or labels.get("mesh.temporary") != "true":
        return False
    expected = {"container": {"fetch", "scan"}, "volume": {"source"}}
    if labels.get("mesh.resource") not in expected.get(kind, set()):
        return False
    pattern = (
        r"mesh-(fetch|scan|keeper)-[a-f0-9]{32}"
        if kind == "container"
        else r"mesh-[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}"
    )
    if not re.fullmatch(pattern, name):
        return False
    created = labels.get("mesh.created-at", "")
    return (
        bool(re.fullmatch(r"[0-9]{10,12}", created)) and 0 < int(created) <= timestamp - minimum_age
    )


def sweep(
    *, apply: bool = False, minimum_age: int = 7200, runner=docker, timestamp=None
) -> SweepReport:
    if minimum_age < 7200:
        raise ValueError("Cleanup age must be at least two hours, beyond the scan lease")
    timestamp = time.time() if timestamp is None else timestamp
    report: SweepReport = {
        "mode": "apply" if apply else "dry_run",
        "eligible": 0,
        "removed": 0,
        "failed": 0,
    }
    for kind in ("container", "volume"):
        arguments = [
            kind,
            "ls",
            "--filter",
            "label=mesh.managed-by=mesh-scanner",
            "--format",
            "{{.ID}}" if kind == "container" else "{{.Name}}",
        ]
        if kind == "container":
            arguments.insert(2, "--all")
        identifiers = runner(arguments).splitlines()
        if len(identifiers) > 1000:
            raise RuntimeError("Cleanup inventory exceeds limit")
        for resource_id in identifiers:
            if not re.fullmatch(
                r"[a-f0-9]{12,64}" if kind == "container" else r"mesh-[a-f0-9-]{36}", resource_id
            ):
                continue
            try:
                objects = json.loads(runner([kind, "inspect", resource_id]))
                if not isinstance(objects, list) or len(objects) != 1:
                    continue
                obj = objects[0]
                name = obj.get("Name", "").lstrip("/")
                labels = (
                    obj.get("Config", {}).get("Labels", {})
                    if kind == "container"
                    else obj.get("Labels", {})
                )
                if not eligible(kind, name, labels or {}, timestamp, minimum_age):
                    continue
                report["eligible"] += 1
                if apply:
                    runner([kind, "rm", "--force", resource_id])
                    report["removed"] += 1
            except (subprocess.SubprocessError, OSError, ValueError, TypeError, AttributeError):
                report["failed"] += 1
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--minimum-age", type=int, default=7200)
    args = parser.parse_args()
    print(json.dumps(sweep(apply=args.apply, minimum_age=args.minimum_age)))
