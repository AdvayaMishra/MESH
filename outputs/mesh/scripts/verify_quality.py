"""Run current-source static/dependency checks and record only actual outcomes."""

import hashlib
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def verify():
    commands = {
        "ruff_lint": ["ruff", "check", "."],
        "ruff_format": ["ruff", "format", "--check", "."],
        "mypy": ["mypy", "backend/app"],
        "bandit": ["bandit", "-r", "backend/app", "-q"],
        "pip_dependency_consistency": ["pip", "check"],
    }
    checks = {}
    for label, arguments in commands.items():
        result = subprocess.run(
            [sys.executable, "-m", *arguments],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=180,
        )
        checks[label] = "passed" if result.returncode == 0 else "failed"
        if result.returncode:
            print(label + ": " + (result.stdout + result.stderr)[-6000:])
    files = sorted((ROOT / "backend/app").rglob("*.py"))
    fingerprint = hashlib.sha256(
        b"".join(
            path.relative_to(ROOT).as_posix().encode()
            + b"\0"
            + hashlib.sha256(path.read_bytes()).digest()
            for path in files
        )
    ).hexdigest()
    return {
        "passed": all(value == "passed" for value in checks.values()),
        "checks": checks,
        "verified_at_utc": datetime.now(UTC).isoformat(),
        "app_python_files": len(files),
        "app_source_fingerprint": fingerprint,
        "limitations": [
            "Static checks and installed dependency consistency only. No claim of vulnerability-free dependencies or production security clearance."
        ],
    }


if __name__ == "__main__":
    report = verify()
    (ROOT / "docs/quality-results.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, indent=2))
    raise SystemExit(0 if report["passed"] else 1)
