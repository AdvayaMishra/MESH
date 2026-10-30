"""Opt-in narrow Auth baseline configuration with private rollback and readback."""

import argparse
import json
import os
import re
import sys
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit

import httpx
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.auth_policy import auth_baseline_patch, evaluate_auth_policy  # noqa: E402


def read_config(client: httpx.Client, url: str, headers: dict) -> dict:
    with client.stream("GET", url, headers=headers, timeout=15, follow_redirects=False) as response:
        if response.status_code != 200:
            raise ValueError("Management read unavailable")
        content = bytearray()
        for chunk in response.iter_bytes(chunk_size=16384):
            content.extend(chunk)
            if len(content) > 1048576:
                raise ValueError("Management response exceeds bounds")
        result = json.loads(content)
        if not isinstance(result, dict):
            raise ValueError("Invalid management response")
        return result


def configure(
    ref: str,
    token: str,
    client: httpx.Client,
    rollback: Path,
    *,
    apply: bool = False,
    settings_only: bool = False,
) -> dict:
    if not re.fullmatch(r"[a-z0-9]{20}", ref) or not token:
        raise ValueError("Verified project and management authority required")
    url = f"https://api.supabase.com/v1/projects/{ref}/config/auth"
    headers = {"Authorization": "Bearer " + token}
    before = read_config(client, url, headers)
    patch = auth_baseline_patch(
        before,
        (ROOT / "supabase/templates/confirmation.html").read_text(encoding="utf-8"),
        (ROOT / "supabase/templates/recovery.html").read_text(encoding="utf-8"),
    )
    deferred = []
    if settings_only:
        deferred = sorted(
            key for key in patch if key.startswith(("mailer_subjects_", "mailer_templates_"))
        )
        patch = {key: value for key, value in patch.items() if key not in deferred}
    report = {
        "status": "planned",
        "changed_fields": sorted(patch),
        "mutations_performed": False,
        "delivery_verified": False,
        "production_clearance": False,
        "deferred_email_fields": deferred,
    }
    if not apply:
        return report
    if not patch:
        return {**report, "status": "already_matches", **evaluate_auth_policy(before)}
    # Exact prior values of only changed fields. Never save raw management config,
    # PAT, SMTP credentials, CAPTCHA secrets or keys. Exclusive creation prevents
    # replacing an earlier rollback record. Keep this file outside source bundles.
    with rollback.open("x", encoding="utf-8") as handle:
        json.dump(
            {"project_ref": ref, "previous_values": {key: before.get(key) for key in patch}},
            handle,
            indent=2,
        )
        handle.write("\n")
    # PATCH is never retried automatically: timeout/failure may have changed state.
    report.update(
        status="patch_outcome_unverified", reconciliation_required=True, mutations_performed=None
    )
    try:
        with client.stream(
            "PATCH", url, json=patch, headers=headers, timeout=15, follow_redirects=False
        ) as response:
            report["patch_http_status"] = response.status_code
            if response.status_code != 200:
                return report
        report["mutations_performed"] = True
        after = read_config(client, url, headers)
        matched = all(after.get(key) == value for key, value in patch.items())
        return {
            **report,
            "status": "applied_and_verified" if matched else "readback_mismatch",
            "readback_matches": matched,
            "reconciliation_required": not matched,
            **evaluate_auth_policy(after),
        }
    except (httpx.HTTPError, ValueError, RecursionError):
        return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument(
        "--settings-only",
        action="store_true",
        help="Defer email subjects/templates pending custom SMTP",
    )
    parser.add_argument(
        "--rollback-file",
        type=Path,
        required=True,
        help="Private operator file outside source/ZIPs",
    )
    args = parser.parse_args()
    load_dotenv(ROOT / ".env")
    operator_file = os.environ.get("MESH_OPERATOR_ENV_FILE")
    if operator_file:
        load_dotenv(operator_file)
    try:
        hostname = urlsplit(os.environ.get("SUPABASE_URL", "")).hostname or ""
        if not re.fullmatch(r"[a-z0-9]{20}\.supabase\.co", hostname):
            raise ValueError("Hosted project identity required")
        with httpx.Client(timeout=15, trust_env=False, follow_redirects=False) as client:
            report = configure(
                hostname.split(".")[0],
                os.environ.get("SUPABASE_ACCESS_TOKEN", ""),
                client,
                args.rollback_file,
                apply=args.apply,
                settings_only=args.settings_only,
            )
    except Exception:
        print(json.dumps({"status": "configuration_not_applied", "production_clearance": False}))
        return 1
    report["checked_at_utc"] = datetime.now(UTC).isoformat()
    (ROOT / "docs/supabase-auth-baseline-results.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, indent=2))
    return 0 if report["status"] in {"planned", "already_matches", "applied_and_verified"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
