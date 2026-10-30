"""Offline production configuration gate; never contacts a service or prints secrets."""

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.production_readiness import inspect_configuration  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, required=True)
    parser.add_argument("--public-url", default="")
    parser.add_argument("--require-directory", action="store_true")
    parser.add_argument("--require-ocr", action="store_true")
    parser.add_argument("--ocr-assessment", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.resolve() == args.env_file.resolve() or (
        args.ocr_assessment and args.output.resolve() == args.ocr_assessment.resolve()
    ):
        print(json.dumps({"status": "refusing_input_overwrite", "production_clearance": False}))
        return 1
    try:
        if args.env_file.stat().st_size > 262144:
            raise ValueError("Oversized configuration")
        values = dotenv_values(args.env_file, interpolate=False)
        assessment = None
        if args.ocr_assessment:
            if args.ocr_assessment.stat().st_size > 4194304:
                raise ValueError("Oversized assessment")
            assessment = json.loads(args.ocr_assessment.read_bytes())
            if not isinstance(assessment, dict):
                raise ValueError("Invalid assessment")
        report = inspect_configuration(
            values,
            public_url=args.public_url or values.get("MESH_PUBLIC_URL") or "",
            require_directory=args.require_directory,
            require_ocr=args.require_ocr,
            ocr_assessment=assessment,
        )
    except (OSError, ValueError, TypeError, RecursionError):
        report = {
            "status": "invalid_input",
            "configuration_baseline_passed": False,
            "production_clearance": False,
        }
    report["checked_at_utc"] = datetime.now(UTC).isoformat()
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if report["configuration_baseline_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
