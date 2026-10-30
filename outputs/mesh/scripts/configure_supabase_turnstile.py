"""Explicitly configure only Turnstile fields; retain private targeted rollback."""

import argparse
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit

import httpx
from configure_supabase_auth_baseline import read_config
from dotenv import dotenv_values


def configure(client, ref, secret, rollback, *, apply=False):
    if not re.fullmatch(r"[a-z0-9]{20}", ref) or not isinstance(secret, str):
        raise ValueError("Project and secret required")
    if not 20 <= len(secret) <= 256 or re.search(r"\s", secret):
        raise ValueError("Invalid key shape")
    url = f"https://api.supabase.com/v1/projects/{ref}/config/auth"
    before = read_config(client, url, {})
    desired = {
        "security_captcha_enabled": True,
        "security_captcha_provider": "turnstile",
        "security_captcha_secret": secret,
    }
    report = {"status": "planned", "mutations_performed": False, "production_clearance": False}
    if all(before.get(key) == value for key, value in desired.items()):
        return {**report, "status": "already_matches", "readback_matches": True}
    if not apply:
        return report
    if before.get("security_captcha_enabled") is True:
        raise ValueError("Refuse to replace an already enabled different CAPTCHA configuration")
    with rollback.open("x", encoding="utf-8") as handle:
        json.dump(
            {"project_ref": ref, "previous_values": {k: before.get(k) for k in desired}}, handle
        )
    report.update(status="patch_outcome_unverified", mutations_performed=None)
    try:
        with client.stream(
            "PATCH", url, json=desired, timeout=20, follow_redirects=False
        ) as response:
            report["patch_http_status"] = response.status_code
            if response.status_code != 200:
                return report
        report["mutations_performed"] = True
        after = read_config(client, url, {})
        matched = all(after.get(k) == v for k, v in desired.items())
        return {
            **report,
            "status": "applied_and_verified" if matched else "readback_mismatch",
            "readback_matches": matched,
        }
    except (httpx.HTTPError, ValueError):
        return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--operator-env", type=Path, required=True)
    parser.add_argument("--runtime-env", type=Path, required=True)
    parser.add_argument("--rollback-file", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    report = {"status": "configuration_unavailable", "production_clearance": False}
    try:
        op = dotenv_values(args.operator_env, interpolate=False)
        env = dotenv_values(args.runtime_env, interpolate=False)
        host = urlsplit(env.get("SUPABASE_URL", "")).hostname or ""
        if not re.fullmatch(r"[a-z0-9]{20}\.supabase\.co", host):
            raise ValueError("Hosted project required")
        if args.output.resolve() in {
            p.resolve() for p in (args.operator_env, args.runtime_env, args.rollback_file)
        }:
            raise ValueError("Output cannot overwrite input or rollback")
        if not op.get("SUPABASE_ACCESS_TOKEN"):
            raise ValueError("Management authority required")
        with httpx.Client(
            headers={"Authorization": "Bearer " + op["SUPABASE_ACCESS_TOKEN"]},
            trust_env=False,
            timeout=20,
            follow_redirects=False,
        ) as client:
            report = configure(
                client,
                host.split(".")[0],
                op.get("TURNSTILE_SECRET_KEY"),
                args.rollback_file,
                apply=args.apply,
            )
    except Exception:
        pass
    report["checked_at_utc"] = datetime.now(UTC).isoformat()
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report))
    return 0 if report["status"] in {"planned", "already_matches", "applied_and_verified"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
