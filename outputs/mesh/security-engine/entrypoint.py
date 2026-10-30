"""Runs only inside the network-free scanner container. Repository code is never imported."""

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path("/repo")
os.chdir(ROOT)


def dependencies():
    from dependencies import extract

    print(json.dumps(extract(ROOT)))


scanner = sys.argv[1]
if scanner == "dependencies":
    dependencies()
    raise SystemExit(0)

if scanner == "semgrep":
    from semgrep_core import scan

    print(
        json.dumps(
            scan(
                ROOT,
                Path("/tmp/scan"),
                Path("/opt/semgrep-core/semgrep-core"),
                Path("/opt/mesh/rules.yml"),
            )
        )
    )
    raise SystemExit(0)

commands = {
    "bandit": [
        "bandit",
        "-r",
        "/repo",
        "-f",
        "json",
        "--ignore-nosec",
        "--ini",
        "/opt/mesh/bandit.ini",
    ],
    "gitleaks": [
        "gitleaks",
        "dir",
        "/repo",
        "--config=/opt/mesh/gitleaks.toml",
        "--gitleaks-ignore-path=/opt/mesh/gitleaks.ignore",
        "--ignore-gitleaks-allow",
        "--redact=100",
        "--report-format=json",
        "--report-path=/tmp/leaks.json",
        "--exit-code=0",
        "--no-banner",
    ],
}
if scanner not in commands:
    raise SystemExit(2)
with open("/tmp/report.json", "wb") as output:
    result = subprocess.run(
        commands[scanner], stdout=output, stderr=subprocess.DEVNULL, timeout=150, check=False
    )
if result.returncode not in ({0, 1} if scanner == "bandit" else {0}):
    raise SystemExit(2)
path = Path("/tmp/leaks.json" if scanner == "gitleaks" else "/tmp/report.json")
if not path.exists():
    if scanner != "gitleaks":
        raise SystemExit(2)
    print("[]")
elif path.stat().st_size > 16 * 1024 * 1024:
    raise SystemExit(2)
else:
    sys.stdout.buffer.write(path.read_bytes())
