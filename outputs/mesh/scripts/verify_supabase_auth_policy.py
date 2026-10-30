"""Read-only Auth management audit. Never persists or prints provider config/secrets."""

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

from app.auth_policy import evaluate_auth_policy  # noqa: E402


def inspect_policy(project_ref: str, token: str, client: httpx.Client) -> dict:
    if not re.fullmatch(r"[a-z0-9]{20}", project_ref):
        return {"status": "invalid_project_reference", "production_clearance": False}
    if not token:
        return {"status": "management_authority_missing", "production_clearance": False}
    try:
        with client.stream(
            "GET",
            f"https://api.supabase.com/v1/projects/{project_ref}/config/auth",
            headers={"Authorization": "Bearer " + token},
            follow_redirects=False,
            timeout=15,
        ) as response:
            if response.status_code != 200:
                return {"status": "management_read_failed", "production_clearance": False}
            content = bytearray()
            for chunk in response.iter_bytes(chunk_size=16384):
                content.extend(chunk)
                if len(content) > 1048576:
                    return {"status": "invalid_management_response", "production_clearance": False}
            config = json.loads(content)
        if not isinstance(config, dict):
            return {"status": "invalid_management_response", "production_clearance": False}
        return {"status": "management_config_read", **evaluate_auth_policy(config)}
    except (httpx.HTTPError, ValueError, RecursionError):
        return {"status": "management_read_failed", "production_clearance": False}


def main() -> int:
    load_dotenv(ROOT / ".env")
    # Optional operator-only file path. No secret command-line arguments.
    operator_file = os.environ.get("MESH_OPERATOR_ENV_FILE")
    if operator_file:
        load_dotenv(operator_file)
    reference = os.environ.get("SUPABASE_PROJECT_REF", "")
    if not reference:
        try:
            hostname = urlsplit(os.environ.get("SUPABASE_URL", "")).hostname or ""
            if re.fullmatch(r"[a-z0-9]{20}\.supabase\.co", hostname):
                reference = hostname.split(".")[0]
        except ValueError:
            pass
    with httpx.Client(timeout=15, follow_redirects=False, trust_env=False) as client:
        report = inspect_policy(reference, os.environ.get("SUPABASE_ACCESS_TOKEN", ""), client)
    report["checked_at_utc"] = datetime.now(UTC).isoformat()
    report["mutations_performed"] = False
    report["delivery_verified"] = False
    (ROOT / "docs/supabase-auth-policy-results.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, indent=2))
    return 0 if report.get("configuration_baseline_passed") else 1


if __name__ == "__main__":
    raise SystemExit(main())
