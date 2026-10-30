"""Real portable clamd with a synthetic signature; not production database validation."""

import argparse
import io
import json
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from dotenv import load_dotenv
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
sys.path.insert(0, str(ROOT / "backend"))
from app.core.config import settings  # noqa: E402
from app.documents import malware_gate  # noqa: E402
from fastapi import HTTPException  # noqa: E402


def verify(executable):
    assert executable.is_absolute() and executable.is_file()
    with tempfile.TemporaryDirectory(prefix="mesh-clamd-fixture-") as folder:
        work = Path(folder)
        marker = b"MESH_SYNTHETIC_BLOCKED_UPLOAD_FIXTURE_2026"
        (work / "mesh.ndb").write_text(
            "Mesh.Synthetic.Blocked:0:*:" + marker.hex() + "\n", encoding="ascii"
        )
        config = work / "clamd.conf"
        config.write_text(
            f"DatabaseDirectory {work.as_posix()}\nTCPSocket 13310\nTCPAddr 127.0.0.1\nForeground yes\nMaxThreads 2\nMaxQueue 4\nStreamMaxLength 2M\nMaxScanTime 10000\nMaxFileSize 2M\nMaxScanSize 10M\n",
            encoding="utf-8",
        )
        settings().clamav_host = "127.0.0.1"
        settings().clamav_port = 13310
        proc = subprocess.Popen(
            [str(executable), "--config-file=" + str(config)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            for _ in range(80):
                if proc.poll() is not None:
                    raise RuntimeError("Clamd startup failed")
                try:
                    with socket.create_connection(("127.0.0.1", 13310), timeout=0.5) as connection:
                        connection.sendall(b"zPING\0")
                        if connection.recv(64).strip(b"\0\r\n") == b"PONG":
                            break
                except OSError:
                    pass
                time.sleep(0.25)
            else:
                raise RuntimeError("Clamd readiness timeout")
            output = io.BytesIO()
            Image.new("RGB", (4, 4), "white").save(output, "PNG")
            malware_gate(output.getvalue())
            try:
                malware_gate(output.getvalue() + marker)
            except HTTPException as exc:
                assert exc.status_code == 422
            else:
                raise AssertionError("Synthetic signature did not reject the fixture")
        finally:
            proc.terminate()
            proc.wait(timeout=15)
        try:
            malware_gate(b"clean fixture")
        except HTTPException as exc:
            assert exc.status_code == 503
        else:
            raise AssertionError("Unavailable engine did not fail closed")
    return {
        "engine": "ClamAV 1.5.4 native Windows",
        "checks": {
            "clamd_ping": "passed",
            "clean_png_cleared": "passed",
            "synthetic_signature_blocked_upload": "passed",
            "engine_shutdown_fails_closed": "passed",
        },
        "signature_scope": "one explicitly synthetic test signature only",
        "production_signature_update": "blocked: FreshClam certificate store unavailable; official CDN HTTP 403",
        "limitations": [
            "No production malware coverage established.",
            "No Docker image or private Supabase Storage upload tested.",
        ],
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--clamd-executable", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = verify(args.clamd_executable)
    except Exception as exc:
        print(json.dumps({"failed": type(exc).__name__}))
        raise SystemExit(1) from None
    (ROOT / "docs/clamav-live-results.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, indent=2))
