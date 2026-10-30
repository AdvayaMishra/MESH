"""Enrich an existing image assessment with Debian release-specific evidence.

Never suppresses findings or approves an image. Does not execute images, install
packages, compare Debian versions or infer runtime exploitability from urgency.
"""

import argparse
import hashlib
import json
import re
import time
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

import httpx

TRACKER_URL = "https://security-tracker.debian.org/tracker/data/json"
RELEASES = {"Debian:12": "bookworm", "Debian:13": "trixie"}
MAX_TRACKER_BYTES = 128 * 1024 * 1024


def download(client: httpx.Client) -> tuple[dict, dict]:
    content = bytearray()
    deadline = time.monotonic() + 90
    with client.stream(
        "GET",
        TRACKER_URL,
        headers={"Accept-Encoding": "identity"},
        timeout=30,
        follow_redirects=False,
    ) as response:
        response.raise_for_status()
        for chunk in response.iter_bytes(chunk_size=65536):
            content.extend(chunk)
            if len(content) > MAX_TRACKER_BYTES or time.monotonic() > deadline:
                raise ValueError("Tracker response exceeded its size/time bound")
        metadata = {
            "url": TRACKER_URL,
            "decoded_sha256": hashlib.sha256(content).hexdigest(),
            "decoded_bytes": len(content),
            "last_modified": response.headers.get("last-modified", "")[:200],
            "transport": "HTTPS verified by the configured client trust store; no signature claim",
        }
    decoded = json.loads(content)
    if not isinstance(decoded, dict) or not decoded:
        raise ValueError("Invalid or empty Debian tracker")
    return decoded, metadata


def bounded_string(data: dict, name: str, limit: int) -> str | None:
    value = data.get(name)
    if value is None:
        return None
    if not isinstance(value, str) or len(value) > limit:
        raise ValueError("Invalid Debian tracker field")
    return value


def evidence(finding: dict, tracker: dict) -> dict:
    result = {
        **finding,
        "review_disposition": "manual_review_required",
        "classification": "tracker_record_missing_or_unsupported",
        "runtime_exploitability": "not_assessed",
        "suppressed": False,
    }
    cve = finding["id"].removeprefix("DEBIAN-")
    release = RELEASES.get(finding["ecosystem"])
    if not release or not re.fullmatch(r"CVE-[0-9]{4}-[0-9]{4,}", cve):
        return result
    result.update(release=release, reference="https://security-tracker.debian.org/tracker/" + cve)
    try:
        package = tracker.get(finding["name"], {})
        advisory = package.get(cve, {})
        record = advisory.get("releases", {}).get(release)
        if record is None:
            return result
        if not isinstance(record, dict):
            raise ValueError("Invalid release entry")
        status = bounded_string(record, "status", 40)
        fixed = bounded_string(record, "fixed_version", 150)
        result.update(
            tracker_status=status,
            fixed_version=fixed,
            urgency=bounded_string(record, "urgency", 100),
            no_dsa_note=bounded_string(record, "nodsa", 2000),
            no_dsa_reason=bounded_string(record, "nodsa_reason", 100),
            scope=bounded_string(advisory, "scope", 100),
        )
        if status == "resolved" and fixed == "0":
            result["classification"] = "upstream_reports_not_affected"
        elif status == "resolved" and fixed:
            result["classification"] = "upstream_fix_requires_installed_version_comparison"
        elif status == "open":
            result["classification"] = "upstream_open"
        elif status == "undetermined":
            result["classification"] = "upstream_undetermined"
        else:
            result["classification"] = "tracker_status_requires_review"
    except (AttributeError, TypeError, ValueError):
        result["classification"] = "tracker_record_invalid"
    return result


def review(assessment: dict, tracker: dict, provenance: dict) -> dict:
    if not isinstance(assessment, dict) or assessment.get("assessment_complete") is not True:
        raise ValueError("A complete installed-image assessment is required")
    identity = assessment.get("immutable_image_id")
    if not isinstance(identity, str) or not re.fullmatch(r"sha256:[a-f0-9]{64}", identity):
        raise ValueError("Immutable assessed image required")
    inventory, findings = assessment.get("packages"), assessment.get("findings")
    if not isinstance(inventory, list) or not 1 <= len(inventory) <= 1000:
        raise ValueError("Invalid source inventory")
    if not isinstance(findings, list) or len(findings) > 10000:
        raise ValueError("Invalid source finding inventory")
    known = set()
    for row in inventory:
        if not isinstance(row, dict) or any(
            not isinstance(row.get(key), str) or not 1 <= len(row[key]) <= 200
            for key in ("ecosystem", "name", "version")
        ):
            raise ValueError("Invalid source package identity")
        known.add(tuple(row[key] for key in ("ecosystem", "name", "version")))
    seen = set()
    for row in findings:
        if not isinstance(row, dict) or any(
            not isinstance(row.get(key), str) or not 1 <= len(row[key]) <= 200
            for key in ("ecosystem", "name", "version", "id")
        ):
            raise ValueError("Invalid source finding")
        binding = tuple(row[key] for key in ("ecosystem", "name", "version"))
        key = (*binding, row["id"])
        if binding not in known or key in seen:
            raise ValueError("Unbound or duplicate source finding")
        seen.add(key)
    if type(assessment.get("vulnerability_references")) is not int or assessment[
        "vulnerability_references"
    ] != len(findings):
        raise ValueError("Incomplete source finding count")
    results = [evidence(row, tracker) for row in findings]
    return {
        "review_complete": True,
        "checked_at_utc": datetime.now(UTC).isoformat(),
        "immutable_image_id": identity,
        "assessment_sha256": hashlib.sha256(
            json.dumps(assessment, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest(),
        "tracker": provenance,
        "findings_retained": len(results),
        "findings_suppressed": 0,
        "classifications": dict(sorted(Counter(row["classification"] for row in results).items())),
        "urgencies": dict(
            sorted(Counter(row.get("urgency") or "unknown" for row in results).items())
        ),
        "production_security_clearance": False,
        "results": results,
        "limitations": [
            "Tracker evidence only; open, low-urgency and upstream-not-affected matches remain retained for human review.",
            "No Debian version comparison, package availability, installed binary reachability or vendor/native library assessment.",
            "This review never changes the original assessment or clean-image gate; no independent signoff is implied.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--assessment", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.assessment.resolve() == args.output.resolve():
            raise ValueError("Review must not overwrite its source assessment")
        if args.assessment.stat().st_size > 4 * 1024 * 1024:
            raise ValueError("Oversized assessment")
        assessment = json.loads(args.assessment.read_bytes())
        with httpx.Client(follow_redirects=False) as client:
            tracker, provenance = download(client)
        report = review(assessment, tracker, provenance)
        code = 0
    except (OSError, ValueError, TypeError, KeyError, RecursionError, httpx.HTTPError) as error:
        report = {
            "review_complete": False,
            "production_security_clearance": False,
            "error_type": type(error).__name__,
        }
        code = 1
    # Refuse destructive source overwrite even when argument validation failed.
    if args.assessment.resolve() == args.output.resolve():
        print(json.dumps(report))
        return 1
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                key: report[key]
                for key in (
                    "review_complete",
                    "findings_retained",
                    "findings_suppressed",
                    "classifications",
                    "error_type",
                )
                if key in report
            }
        )
    )
    return code


if __name__ == "__main__":
    raise SystemExit(main())
