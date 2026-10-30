"""Opt-in OSV assessment of Debian source packages in an operator-trusted image.

Never runs a repository image. Containers receive no mounts, credentials or
network. Only installed OS package names/versions are submitted to OSV.
"""

import argparse
import json
import re
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import httpx

PROBE = """
import json, pathlib
release = dict(line.split('=', 1) for line in pathlib.Path('/etc/os-release').read_text().splitlines() if '=' in line)
print(json.dumps({'release': release, 'status': pathlib.Path('/var/lib/dpkg/status').read_text()}))
"""


def packages(probe: dict) -> list[dict]:
    release = probe["release"]
    version = release.get("VERSION_ID", "").strip('"')
    if release.get("ID", "").strip('"') != "debian" or not re.fullmatch(r"[0-9]{1,2}", version):
        raise ValueError("Only versioned Debian package inventories are supported")
    status = probe["status"]
    if not isinstance(status, str) or len(status) > 4 * 1024 * 1024:
        raise ValueError("Invalid package database size")
    inventory = set()
    for paragraph in status.strip().split("\n\n"):
        fields = {}
        for line in paragraph.splitlines():
            if line and not line.startswith((" ", "\t")) and ": " in line:
                key, value = line.split(": ", 1)
                fields[key] = value
        if fields.get("Status") != "install ok installed":
            continue
        source = fields.get("Source", fields.get("Package", ""))
        match = re.fullmatch(r"([a-z0-9][a-z0-9+.-]{0,199})(?: \(([^)]+)\))?", source)
        if match is None:
            raise ValueError("Invalid source package identity")
        source_version = match[2] or fields.get("Version", "")
        if not re.fullmatch(r"[A-Za-z0-9:.+~_-]{1,150}", source_version):
            raise ValueError("Invalid Debian package version")
        inventory.add((match[1], source_version))
    if not inventory or len(inventory) > 1000:
        raise ValueError("Empty or excessive Debian inventory")
    return [
        {"ecosystem": "Debian:" + version, "name": name, "version": value}
        for name, value in sorted(inventory)
    ]


def query(client: httpx.Client, inventory: list[dict]) -> list[dict]:
    findings = []
    for start in range(0, len(inventory), 100):
        active = [
            (
                item,
                {
                    "package": {"ecosystem": item["ecosystem"], "name": item["name"]},
                    "version": item["version"],
                },
            )
            for item in inventory[start : start + 100]
        ]
        for _ in range(20):
            with client.stream(
                "POST",
                "https://api.osv.dev/v1/querybatch",
                json={"queries": [request for _, request in active]},
                timeout=30,
                follow_redirects=False,
            ) as response:
                response.raise_for_status()
                content = bytearray()
                for chunk in response.iter_bytes(chunk_size=16384):
                    content.extend(chunk)
                    if len(content) > 4 * 1024 * 1024:
                        raise ValueError("OSV response limit exceeded")
            decoded = json.loads(content)
            results = decoded.get("results") if isinstance(decoded, dict) else None
            if not isinstance(results, list) or len(results) != len(active):
                raise ValueError("Incomplete OSV assessment")
            next_page = []
            for (item, request), result in zip(active, results, strict=True):
                if not isinstance(result, dict) or "error" in result:
                    raise ValueError("OSV query failed")
                vulns = result.get("vulns", [])
                if not isinstance(vulns, list):
                    raise ValueError("Invalid vulnerability list")
                for vuln in vulns:
                    if (
                        not isinstance(vuln, dict)
                        or not isinstance(vuln.get("id"), str)
                        or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,200}", str(vuln.get("id", "")))
                    ):
                        raise ValueError("Invalid vulnerability identifier")
                    findings.append({**item, "id": vuln["id"]})
                    if len(findings) > 10000:
                        raise ValueError("Vulnerability inventory exceeded bound")
                token = result.get("next_page_token")
                if token is not None:
                    if not isinstance(token, str) or not 1 <= len(token) <= 4096:
                        raise ValueError("Invalid OSV pagination")
                    next_page.append((item, {**request, "page_token": token}))
            if not next_page:
                break
            active = next_page
        else:
            raise ValueError("OSV pagination limit exceeded")
    return [dict(item) for item in {tuple(sorted(item.items())) for item in findings}]


def verify(docker: Path, image: str, trusted: bool) -> dict:
    if not trusted or not docker.is_absolute() or not docker.is_file():
        raise ValueError("Explicit trusted image and absolute Docker executable required")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_./:@-]{0,254}", image):
        raise ValueError("Invalid trusted image reference")

    def run(arguments):
        result = subprocess.run(
            [str(docker), *arguments], capture_output=True, timeout=120, check=True
        )
        if len(result.stdout) > 5 * 1024 * 1024:
            raise ValueError("Image inventory exceeded bound")
        return result.stdout

    identity = run(["image", "inspect", "--format", "{{.Id}}", image]).decode().strip()
    if not re.fullmatch(r"sha256:[a-f0-9]{64}", identity):
        raise ValueError("Invalid immutable image identity")
    name = "mesh-os-audit-" + uuid4().hex
    command = [
        "run",
        "--rm",
        "--name",
        name,
        "--network=none",
        "--read-only",
        "--user=10001",
        "--cap-drop=ALL",
        "--security-opt=no-new-privileges",
        "--pids-limit=32",
        "--memory=128m",
        "--memory-swap=128m",
        "--cpus=0.5",
    ]
    for variable in ["http_proxy", "https_proxy", "all_proxy", "no_proxy", "ftp_proxy"]:
        command.extend(["--env", variable + "=", "--env", variable.upper() + "="])
    try:
        probe = json.loads(run([*command, "--entrypoint=python", identity, "-c", PROBE]))
    finally:
        subprocess.run([str(docker), "rm", "--force", name], capture_output=True, timeout=30)
    inventory = packages(probe)
    with httpx.Client(follow_redirects=False) as client:
        findings = query(client, inventory)
    return {
        "assessment_complete": True,
        "passed": not findings,
        "image": image,
        "immutable_image_id": identity,
        "checked_at": datetime.now(UTC).isoformat(),
        "packages_checked": len(inventory),
        "packages": inventory,
        "vulnerability_references": len(findings),
        "findings": sorted(findings, key=lambda item: (item["name"], item["id"])),
        "limitations": [
            "Debian installed source-package metadata only; OSV advisory coverage at execution time.",
            "Does not assess vendored native libraries, compiled Python, wheel-bundled libraries, Gitleaks or Semgrep native internals.",
            "Advisory matches require applicability and fixed-version review; absence is not proof of safety.",
        ],
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--docker-executable", type=Path, required=True)
    parser.add_argument("--image", required=True)
    parser.add_argument("--trusted-operator-image", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = verify(args.docker_executable, args.image, args.trusted_operator_image)
    except Exception as error:
        report = {"assessment_complete": False, "passed": False, "error_type": type(error).__name__}
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                key: report[key]
                for key in [
                    "assessment_complete",
                    "passed",
                    "packages_checked",
                    "vulnerability_references",
                    "error_type",
                ]
                if key in report
            }
        )
    )
    raise SystemExit(0 if report["passed"] else 1)
