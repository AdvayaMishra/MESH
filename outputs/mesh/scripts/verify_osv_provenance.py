"""Explicit read-only OSV provenance acceptance; sends public package triples only."""

import argparse
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

import httpx
from packaging.requirements import Requirement

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
os.environ.update(TEST_MODE="true", DATABASE_URL="sqlite://")

from app.scanning import OSV  # noqa: E402


def verify():
    packages = []
    for line in (ROOT / "requirements.lock").read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        requirement = Requirement(line)
        pins = list(requirement.specifier)
        if len(pins) != 1 or pins[0].operator != "==" or requirement.url:
            raise ValueError("Exact public runtime pins required")
        packages.append({"name": requirement.name, "ecosystem": "PyPI", "version": pins[0].version})
    requests = 0

    def outbound(request):
        nonlocal requests
        if (
            str(request.url) != "https://api.osv.dev/v1/querybatch"
            or "authorization" in request.headers
            or "cookie" in request.headers
        ):
            raise ValueError("Unexpected OSV destination or credentials")
        data = json.loads(request.content)
        if set(data) != {"queries"}:
            raise ValueError("Unexpected OSV payload")
        for query in data["queries"]:
            if set(query) - {"package", "version", "page_token"} or set(query["package"]) != {
                "name",
                "ecosystem",
            }:
                raise ValueError("Non-package metadata in OSV payload")
        requests += 1

    fixture = {"name": "Django", "ecosystem": "PyPI", "version": "2.2.0"}
    with httpx.Client(
        timeout=15, follow_redirects=False, event_hooks={"request": [outbound]}
    ) as client:
        runtime = OSV(client).check(packages)
        vulnerable = OSV(client).check([fixture])
    allowed = {(p["name"], p["ecosystem"], p["version"]) for p in packages}
    assert all(
        (row["dependency"]["name"], row["dependency"]["ecosystem"], row["dependency"]["version"])
        in allowed
        for row in runtime
    )
    assert vulnerable and all(row["dependency"] == fixture for row in vulnerable)
    return {
        "assessment_complete": True,
        "passed": True,
        "verified_at_utc": datetime.now(UTC).isoformat(),
        "runtime_packages_checked": len(packages),
        "runtime_advisory_observations": len(runtime),
        "runtime_clean_gate_passed": not runtime,
        "known_vulnerable_fixture_advisories": len(vulnerable),
        "exact_package_ecosystem_version_retained": True,
        "only_public_package_metadata_sent": True,
        "http_requests": requests,
        "limitations": [
            "Actual public OSV requests only; no GitHub checkout, repository source or credentials were sent.",
            "Positive fixture detection and metadata association are assessed separately from the runtime clean gate.",
            "OSV batch advisory identifiers are not CVSS severity enrichment; displayed info is a placeholder.",
            "Availability/advisory coverage at execution time only; absence of matches is not production security clearance.",
        ],
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--allow-public-package-queries", action="store_true", required=True)
    parser.parse_args()
    try:
        result = verify()
    except Exception as error:
        result = {"assessment_complete": False, "passed": False, "error_type": type(error).__name__}
    (ROOT / "docs/osv-provenance-live-results.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result["passed"] else 1)
