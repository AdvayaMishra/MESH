"""Opt-in isolated OCR evaluation on an authorized local corpus, aggregate output only."""

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))


def immutable_image_reference(value: str) -> bool:
    return bool(
        re.fullmatch(
            r"(?:sha256:[a-f0-9]{64}|[A-Za-z0-9][A-Za-z0-9./_:-]*@sha256:[a-f0-9]{64})", value
        )
    )


def dataset(manifest: Path) -> list[tuple[Path, dict]]:
    with manifest.open("rb") as handle:
        content = handle.read(1048577)
    if len(content) > 1048576:
        raise ValueError("Dataset manifest exceeds bound")
    rows = json.loads(content)
    if not isinstance(rows, list) or not 1 <= len(rows) <= 1000:
        raise ValueError("Dataset requires 1 to 1000 entries")
    base = manifest.resolve().parent
    entries = []
    seen = set()
    total = 0
    for row in rows:
        if not isinstance(row, dict) or set(row) != {
            "image",
            "expected_name",
            "expected_employee_id",
        }:
            raise ValueError("Invalid dataset entry")
        relative = row["image"]
        if not isinstance(relative, str) or not relative or Path(relative).is_absolute():
            raise ValueError("Dataset images require relative paths")
        path = (base / relative).resolve()
        if not path.is_relative_to(base) or path in seen or not path.is_file():
            raise ValueError("Dataset images must be unique files inside the corpus")
        seen.add(path)
        total += path.stat().st_size
        if path.stat().st_size > 2097152 or total > 67108864:
            raise ValueError("Dataset image bounds exceeded")
        for field, limit in (("expected_name", 100), ("expected_employee_id", 50)):
            value = row[field]
            if value is not None and (
                not isinstance(value, str) or not value.strip() or len(value) > limit
            ):
                raise ValueError("Invalid expected OCR field")
        entries.append((path, row))
    return entries


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--docker-executable", type=Path, required=True)
    parser.add_argument(
        "--image", required=True, help="Existing local immutable OCR image ID or repository digest"
    )
    parser.add_argument(
        "--authorized-dataset", action="store_true", help="Operator confirms corpus authorization"
    )
    args = parser.parse_args()
    if not args.authorized_dataset:
        print(
            json.dumps({"status": "dataset_authorization_required", "production_clearance": False})
        )
        return 1
    try:
        if not args.docker_executable.is_absolute() or not immutable_image_reference(args.image):
            raise ValueError("Absolute Docker path and digest-pinned image required")
        entries = dataset(args.manifest)
        os.environ.update(
            TEST_MODE="true",
            DATABASE_URL="sqlite://",
            DOCKER_EXECUTABLE=str(args.docker_executable),
            DOCUMENT_OCR_IMAGE=args.image,
        )
        from app.core.config import settings
        from app.document_ocr import OCRSandbox, Suggestions
        from app.documents import validate_image
        from app.ocr_evaluation import evaluate_samples

        settings.cache_clear()
        inspected = (
            subprocess.run(
                [
                    str(args.docker_executable),
                    "image",
                    "inspect",
                    args.image,
                    "--format",
                    "{{.Id}}",
                ],
                capture_output=True,
                timeout=20,
                check=True,
            )
            .stdout.decode()
            .strip()
        )
        if not re.fullmatch(r"sha256:[a-f0-9]{64}", inspected):
            raise ValueError("Invalid image fingerprint")
        if args.image.startswith("sha256:") and inspected != args.image:
            raise ValueError("Local immutable image identity did not match")
        values = []
        sandbox = OCRSandbox()
        for path, row in entries:
            # Bounds are checked again on the actual bytes before daemon input.
            with path.open("rb") as handle:
                content = handle.read(2097153)
            media = "image/png" if content.startswith(b"\x89PNG") else "image/jpeg"
            validate_image(content, media)
            expected = Suggestions(
                suggested_name=row["expected_name"],
                suggested_employee_id=row["expected_employee_id"],
                engine="ground-truth",
            )
            values.append((expected, sandbox.analyze(content)))
        report = evaluate_samples(values)
        report.update(status="evaluated", image_id=inspected, image_reference=args.image)
        print(json.dumps(report, indent=2))
        return 0
    except Exception:
        # Corpus paths, expected identities, engine errors and credentials stay private.
        print(json.dumps({"status": "evaluation_failed", "production_clearance": False}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
