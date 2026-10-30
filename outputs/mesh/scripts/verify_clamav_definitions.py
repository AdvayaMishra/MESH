"""Official signature database verification and real clamd/EICAR acceptance.

Uses an operator-supplied directory populated by official cvdupdate/FreshClam.
EICAR is assembled in memory and sent over loopback; no malware file is saved.
"""

import argparse
import io
import json
import re
import socket
import subprocess
import sys
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path

from dotenv import load_dotenv
from fastapi import HTTPException
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
sys.path.insert(0, str(ROOT / "backend"))
from app.core.config import settings  # noqa: E402
from app.documents import malware_gate  # noqa: E402


def verify(executable, database):
    assert executable.is_absolute() and executable.is_file()
    assert database.is_absolute() and database.is_dir()
    versions = {}
    for name in ["main", "daily", "bytecode"]:
        info = subprocess.run(
            [str(executable.with_name("sigtool.exe")), "--info=" + str(database / (name + ".cvd"))],
            capture_output=True,
            text=True,
            timeout=30,
            check=True,
        ).stdout
        assert "Verification OK." in info
        version = int(re.search(r"^Version: (\d+)$", info, re.M).group(1))
        built = datetime.strptime(
            re.search(r"^Build time: (.+)$", info, re.M).group(1), "%d %b %Y %H:%M %z"
        )
        if name == "daily":
            assert 0 <= (datetime.now(UTC) - built).total_seconds() <= 72 * 3600
        versions[name] = {
            "version": version,
            "built_at_utc": built.astimezone(UTC).isoformat(),
            "digital_signature_verified": True,
        }
    with tempfile.TemporaryDirectory(prefix="mesh-official-clamd-") as folder:
        config = Path(folder) / "clamd.conf"
        config.write_text(
            f"DatabaseDirectory {database.as_posix()}\nTCPSocket 13310\nTCPAddr 127.0.0.1\nForeground yes\nMaxThreads 2\nMaxQueue 4\nStreamMaxLength 2M\nMaxScanTime 10000\nMaxFileSize 2M\nMaxScanSize 10M\nAlertExceedsMax yes\n",
            encoding="utf-8",
        )
        settings().clamav_host = "127.0.0.1"
        settings().clamav_port = 13310
        process = subprocess.Popen(
            [str(executable), "--config-file=" + str(config)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            for _ in range(160):
                if process.poll() is not None:
                    raise RuntimeError("Clamd exited before readiness")
                try:
                    with socket.create_connection(("127.0.0.1", 13310), timeout=0.5) as connection:
                        connection.sendall(b"zPING\0")
                        if connection.recv(64).strip(b"\0\r\n") == b"PONG":
                            break
                except OSError:
                    pass
                time.sleep(0.25)
            else:
                raise RuntimeError("Clamd startup timed out")
            output = io.BytesIO()
            Image.new("RGB", (4, 4), "white").save(output, "PNG")
            malware_gate(output.getvalue())
            eicar = (
                b"X5O!P%@AP[4\\" + b"PZX54(P^)7CC)7}$" + b"EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*"
            )
            assert len(eicar) == 68
            try:
                malware_gate(eicar)
            except HTTPException as exc:
                assert exc.status_code == 422
            else:
                raise AssertionError("EICAR test was not detected")
        finally:
            process.terminate()
            process.wait(timeout=15)
        try:
            malware_gate(b"clean")
        except HTTPException as exc:
            assert exc.status_code == 503
        else:
            raise AssertionError("Shutdown did not fail closed")
    return {
        "verified_at_utc": datetime.now(UTC).isoformat(),
        "checks": {
            "official_database_digital_signatures": "passed",
            "daily_database_age_under_72_hours": "passed",
            "real_engine_ping_and_clean_png": "passed",
            "official_eicar_detection_through_upload_gate": "passed",
            "engine_shutdown_fails_closed": "passed",
        },
        "databases": versions,
        "limitations": [
            "Native official Windows engine; Docker image not run.",
            "Current definitions do not prove complete malware coverage; operational updating remains required.",
        ],
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--clamd-executable", type=Path, required=True)
    parser.add_argument("--database-directory", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = verify(args.clamd_executable, args.database_directory)
    except Exception as exc:
        print(json.dumps({"failed": type(exc).__name__}))
        raise SystemExit(1) from None
    (ROOT / "docs/clamav-definitions-results.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(result, indent=2))
