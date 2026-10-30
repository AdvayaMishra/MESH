"""Query OSV with public scanner package metadata; never installs or executes a repository."""

import json
import re
from datetime import UTC, datetime
from pathlib import Path

from app.scanning import OSV

ROOT = Path(__file__).resolve().parents[1]


def verify() -> dict:
    packages = []
    lines = "\n".join(
        (ROOT / "security-engine" / name).read_text()
        for name in ("requirements.lock", "semgrep-artifact.lock")
    )
    for line in lines.splitlines():
        if not line or line.startswith(("#", "--")):
            continue
        match = re.fullmatch(
            r"([A-Za-z0-9_.-]+)==([A-Za-z0-9.+_-]+) --hash=sha256:[a-f0-9]{64}", line
        )
        if match is None:
            raise ValueError("Invalid scanner hash lock")
        packages.append({"ecosystem": "PyPI", "name": match[1], "version": match[2]})
    if not packages:
        raise ValueError("Empty scanner inventory")
    findings = OSV().check(packages)
    return {
        "assessment_complete": True,
        "packages_checked": len(packages),
        "scope": "Seven final-image Python packages plus the official native Semgrep artifact; its unused Python frontend dependencies are excluded.",
        "vulnerability_references": len(findings),
        "vulnerability_ids": sorted({finding["rule_id"] for finding in findings}),
        "passed": not findings,
        "limitations": [
            "Public exact package metadata only; no source, credentials or evidence submitted.",
            "OSV assessment at execution time; base OS, vendored native binaries and future vulnerabilities are separate.",
        ],
    }


if __name__ == "__main__":
    try:
        report = verify()
    except Exception as error:
        report = {"assessment_complete": False, "passed": False, "error": type(error).__name__}
    report["checked_at"] = datetime.now(UTC).isoformat()
    (ROOT / "docs/scanner-dependency-audit.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, indent=2))
    raise SystemExit(0 if report["passed"] else 1)
