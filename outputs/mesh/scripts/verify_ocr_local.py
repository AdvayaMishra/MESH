"""Actual isolated OCR, fictional image only; no hosted credentials or real identity data."""

import argparse
import hashlib
import io
import json
import os
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]


def verify(args):
    os.environ.update(
        TEST_MODE="true",
        DATABASE_URL="sqlite://",
        DOCKER_EXECUTABLE=str(Path(args.docker_executable).resolve()),
        DOCUMENT_OCR_IMAGE=args.image,
    )
    sys.path.insert(0, str(ROOT / "backend"))
    from app.core.config import settings
    from app.document_ocr import OCRSandbox

    settings.cache_clear()
    docker = str(Path(args.docker_executable).resolve())
    fingerprint = (
        subprocess.run(
            [docker, "image", "inspect", args.image, "--format", "{{.Id}}"],
            capture_output=True,
            check=True,
            timeout=20,
        )
        .stdout.decode()
        .strip()
    )
    image = Image.new("RGB", (1000, 240), "white")
    draw = ImageDraw.Draw(image)
    font = ImageFont.truetype(args.font, 42)
    draw.text((35, 35), "Name: Synthetic Tester", font=font, fill="black")
    draw.text((35, 110), "Employee ID: MESH-TEST-42", font=font, fill="black")
    payload = io.BytesIO()
    image.save(payload, "PNG")
    sandbox = OCRSandbox()
    result = sandbox.analyze(payload.getvalue())
    assert (
        result.suggested_name == "Synthetic Tester"
        and result.suggested_employee_id == "MESH-TEST-42"
    )
    assert result.untrusted is True
    command = sandbox.command("mesh-scan-fixture", "stdin", "ocr")
    assert all(
        flag in command
        for flag in [
            "--log-driver=none",
            "--network=none",
            "--read-only",
            "--cap-drop=ALL",
            "--memory-swap=512m",
        ]
    )
    assert "--mount" not in command
    metadata = subprocess.run(
        [
            docker,
            "run",
            "--rm",
            "--network=none",
            "--read-only",
            "--cap-drop=ALL",
            "--security-opt=no-new-privileges",
            "--user=10001:10001",
            "--entrypoint=python",
            args.image,
            "-c",
            "import hashlib,json,pathlib,subprocess; print(json.dumps({'version':subprocess.check_output(['tesseract','--version']).decode().splitlines()[0], 'eng_sha256':hashlib.sha256(pathlib.Path('/usr/share/tesseract-ocr/5/tessdata/eng.traineddata').read_bytes()).hexdigest(), 'wrapper_sha256':hashlib.sha256(pathlib.Path('/opt/mesh/ocr.py').read_bytes()).hexdigest()}))",
        ],
        capture_output=True,
        check=True,
        timeout=30,
    )
    engine = json.loads(metadata.stdout)
    assert engine["version"] == "tesseract 5.5.0"
    assert (
        engine["wrapper_sha256"]
        == hashlib.sha256((ROOT / "security-engine/ocr.py").read_bytes()).hexdigest()
    )
    checks = {
        "real_tesseract_inference_fictional_png": True,
        "english_labeled_candidates_only": True,
        "required_daemon_isolation_controls_verified": True,
        "stdin_only_no_host_mounts_or_keys": True,
        "persistent_container_logs_disabled": True,
        "engine_and_language_fingerprint": True,
    }
    if args.private_storage:
        from app.documents import PrivateStorage
        from app.ocr_worker import analyze

        key = "/".join(str(uuid4()) for _ in range(3))
        storage = PrivateStorage()
        try:
            storage.upload(key, payload.getvalue(), "image/png")
            private_result = analyze(key, hashlib.sha256(payload.getvalue()).hexdigest())
            assert private_result.suggested_name == "Synthetic Tester"
            assert private_result.suggested_employee_id == "MESH-TEST-42"
            checks["actual_private_storage_download_digest_and_isolated_ocr"] = True
        finally:
            storage.delete(key)  # Only this generated fictional-image path is eligible for cleanup.
            checks["generated_storage_object_removed"] = True
    return {
        "passed": all(checks.values()),
        "checks": checks,
        "immutable_image_id": fingerprint,
        "engine": engine,
        "wrapper_sha256": hashlib.sha256(
            (ROOT / "security-engine/ocr.py").read_bytes()
        ).hexdigest(),
        "limitations": [
            "Synthetic English fixture only, not real-ID accuracy or multilingual validation.",
            "Worker leases/encryption/HR authorization are separately tested; this is not a real employee upload.",
            "OS vulnerability assessment and production security clearance are separate.",
        ],
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--docker-executable", required=True)
    parser.add_argument("--image", default="mesh-ocr:local")
    parser.add_argument("--font", required=True)
    parser.add_argument(
        "--private-storage",
        action="store_true",
        help="Opt in to uploading/removing one fictional fixture with configured backend Storage credentials",
    )
    parser.add_argument("--output", default=str(ROOT / "docs/ocr-live-results.json"))
    args = parser.parse_args()
    try:
        report = verify(args)
    except Exception as error:
        report = {"passed": False, "error_type": type(error).__name__}
    Path(args.output).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report))
    raise SystemExit(0 if report["passed"] else 1)
