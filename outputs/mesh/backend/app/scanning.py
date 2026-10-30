"""Scanner execution exclusively inside constrained Docker containers, never on API host."""

import json
import queue
import re
import subprocess  # nosec B404 # deliberate Docker-only launcher; never executes repository code
import threading
import time
from pathlib import PurePosixPath
from typing import Any
from uuid import uuid4

import httpx

from app.core.config import settings
from app.security import sanitized_scanner_finding


def resource_labels(kind: str) -> list[str]:
    if kind not in {"source", "fetch", "scan"}:
        raise ValueError("Unknown managed scanner resource")
    return [
        "--label",
        "mesh.managed-by=mesh-scanner",
        "--label",
        "mesh.temporary=true",
        "--label",
        "mesh.resource=" + kind,
        "--label",
        "mesh.created-at=" + str(int(time.time())),
    ]


def normalize(scanner: str, report: Any) -> list[dict]:
    if isinstance(report, dict) and report.get("errors"):
        raise ValueError("Scanner reported incomplete analysis")
    findings = []
    if scanner == "semgrep":
        rows = report.get("results", [])
        for row in rows:
            findings.append(
                {
                    "path": row["path"],
                    "line": row.get("start", {}).get("line", 1),
                    "column": row.get("start", {}).get("col"),
                    "rule_id": row["check_id"],
                    "severity": {"ERROR": "high", "WARNING": "medium", "INFO": "low"}.get(
                        row.get("extra", {}).get("severity"), "info"
                    ),
                }
            )
    elif scanner == "bandit":
        for row in report.get("results", []):
            findings.append(
                {
                    "path": row["filename"],
                    "line": row["line_number"],
                    "column": row["col_offset"] + 1
                    if type(row.get("col_offset")) is int
                    else row.get("col_offset"),
                    "rule_id": row["test_id"],
                    "severity": row["issue_severity"].lower(),
                }
            )
    elif scanner == "gitleaks":
        for row in report:
            findings.append(
                {
                    "path": row["File"],
                    "line": row["StartLine"],
                    "column": row.get("StartColumn") or None,
                    "rule_id": row["RuleID"],
                    "severity": "high",
                }
            )
    else:
        raise ValueError("Unsupported scanner")
    normalized = []
    if len(findings) > 10000:
        raise ValueError("Scanner finding count exceeded limit")
    for finding in findings:
        path = finding["path"].replace("\\", "/")
        if path.startswith("/repo/"):
            path = path[6:]
        if path.startswith("/tmp/scan/"):  # nosec B108 # string normalization of a reported container path; no file is created
            path = path[10:]
        if path.startswith("./"):
            path = path[2:]
        finding["path"] = str(PurePosixPath(path))
        normalized.append(sanitized_scanner_finding(scanner, finding))
    return normalized


def validate_docker_host(capabilities: Any) -> None:
    if (
        not isinstance(capabilities, dict)
        or capabilities.get("os") != "linux"
        or capabilities.get("arch") not in {"x86_64", "amd64"}
    ):
        raise ValueError("Linux amd64 scanner host required")
    if any(
        capabilities.get(name) is not True for name in ("memory", "swap", "cpu", "period", "pids")
    ):
        raise ValueError("Required cgroup resource control is unavailable")
    security = capabilities.get("security")
    if not isinstance(security, list) or "name=seccomp,profile=builtin" not in security:
        raise ValueError("Default seccomp confinement required")


class DockerSandbox:
    def __init__(
        self,
        image: str = "mesh-scanner:local",
        timeout: int = 180,
        max_output: int = 16 * 1024 * 1024,
    ):
        self.image, self.timeout, self.max_output = image, timeout, max_output
        self._host_verified = False

    def verify_host(self) -> None:
        if self._host_verified:
            return
        # Stable JSON API keys avoid CLI Go-field capitalization differences.
        # Raw daemon metadata may contain proxy settings: never log or retain it.
        template = "{{json .}}"
        try:
            result = subprocess.run(  # nosec B603 # fixed operator Docker binary and fixed read-only info template
                [settings().docker_executable, "info", "--format", template],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                timeout=15,
                check=True,
            )
            if len(result.stdout) > 65536:
                raise ValueError("Host response exceeds bound")
            raw = json.loads(result.stdout)
            if not isinstance(raw, dict):
                raise ValueError("Invalid host metadata")
            keys = {
                "os": "OSType",
                "arch": "Architecture",
                "memory": "MemoryLimit",
                "swap": "SwapLimit",
                "cpu": "CpuCfsQuota",
                "period": "CpuCfsPeriod",
                "pids": "PidsLimit",
                "security": "SecurityOptions",
            }
            capabilities = {name: raw.get(key) for name, key in keys.items()}
            validate_docker_host(capabilities)
        except (OSError, subprocess.SubprocessError, ValueError, TypeError):
            raise RuntimeError(
                "Scanner Docker host lacks required Linux isolation/resource controls"
            ) from None
        self._host_verified = True

    def command(self, name: str, volume: str, scanner: str) -> list[str]:
        if scanner not in {"bandit", "semgrep", "gitleaks", "dependencies"} or not re.fullmatch(
            r"mesh-[a-f0-9-]+", volume
        ):
            raise ValueError("Invalid scanner or owned volume")
        return [
            settings().docker_executable,
            "run",
            "--name",
            name,
            *resource_labels("scan"),
            "--rm",
            "--pull=never",
            "--network=none",
            "--read-only",
            "--cap-drop=ALL",
            "--security-opt=no-new-privileges",
            "--pids-limit=128",
            "--memory=768m",
            "--memory-swap=768m",
            "--cpus=1",
            "--ulimit=nofile=256:256",
            "--user=10001:10001",
            # Docker client proxy defaults may contain operator credentials.
            # Explicit empty values prevent automatic injection into analysis.
            *[
                argument
                for name in (
                    "HTTP_PROXY",
                    "HTTPS_PROXY",
                    "FTP_PROXY",
                    "ALL_PROXY",
                    "NO_PROXY",
                    "http_proxy",
                    "https_proxy",
                    "ftp_proxy",
                    "all_proxy",
                    "no_proxy",
                )
                for argument in ("--env", name + "=")
            ],
            "--tmpfs=/tmp:rw,noexec,nosuid,size=128m",
            "--mount",
            f"type=volume,src={volume},dst=/repo,readonly",
            self.image,
            scanner,
        ]

    def execute(self, volume: str, scanner: str, input_bytes: bytes | None = None) -> Any:
        if input_bytes is not None and len(input_bytes) > 2097152:
            raise ValueError("Sandbox input exceeded limit")
        self.verify_host()
        name = "mesh-scan-" + uuid4().hex
        input_options: dict[str, Any] = (
            {"stdin": subprocess.PIPE} if input_bytes is not None else {}
        )
        process = subprocess.Popen(  # nosec B603 # fixed Docker binary and validated container argument vector; shell is disabled
            self.command(name, volume, scanner),
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            **input_options,
        )
        chunks: queue.Queue[bytes | None] = queue.Queue(maxsize=2)
        stopped = threading.Event()

        def read():
            if process.stdout is None:
                return
            while not stopped.is_set():
                chunk = process.stdout.read(65536)
                while not stopped.is_set():
                    try:
                        chunks.put(chunk if chunk else None, timeout=0.1)
                        break
                    except queue.Full:
                        continue
                if not chunk:
                    break

        reader = threading.Thread(target=read, daemon=True)
        reader.start()

        def write():
            if process.stdin is not None:
                try:
                    process.stdin.write(input_bytes or b"")
                    process.stdin.close()
                except (BrokenPipeError, OSError):
                    pass

        writer = threading.Thread(target=write, daemon=True) if input_bytes is not None else None
        if writer:
            writer.start()
        output = bytearray()
        deadline = time.monotonic() + self.timeout
        try:
            while time.monotonic() < deadline:
                try:
                    chunk = chunks.get(timeout=0.1)
                except queue.Empty:
                    continue
                if chunk is None:
                    break
                output.extend(chunk)
                if len(output) > self.max_output:
                    raise RuntimeError("Scanner output exceeded limit")
            else:
                raise TimeoutError("Scanner exceeded time limit")
            if process.wait(timeout=5) != 0:
                raise RuntimeError("Scanner failed; raw diagnostics suppressed")
            return json.loads(output)
        finally:
            stopped.set()
            if process.poll() is None:
                process.kill()
            process.wait(timeout=10)
            subprocess.run(  # nosec B603 # fixed cleanup command and generated container name
                [settings().docker_executable, "rm", "-f", name],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=15,
                check=False,
            )
            reader.join(timeout=2)
            if writer:
                writer.join(timeout=2)
            if process.stdout:
                process.stdout.close()


class OSV:
    """Only package name, ecosystem and exact version leave the isolated checkout."""

    def __init__(self, client: httpx.Client | None = None):
        self.client = client

    def check(self, dependencies: list[dict]) -> list[dict]:
        if len(dependencies) > 500:
            raise ValueError("Dependency count exceeds limit")
        queries = []
        for package in dependencies:
            if (
                not isinstance(package, dict)
                or not isinstance(package.get("name"), str)
                or not isinstance(package.get("version"), str)
                or package.get("ecosystem") not in {"PyPI", "npm"}
                or not re.fullmatch(r"[A-Za-z0-9@_./-]{1,200}", package.get("name", ""))
                or not re.fullmatch(r"[A-Za-z0-9.+_-]{1,100}", package.get("version", ""))
            ):
                raise ValueError("Unsupported dependency metadata")
            queries.append(
                {
                    "package": {"name": package["name"], "ecosystem": package["ecosystem"]},
                    "version": package["version"],
                }
            )
        if not queries:
            return []

        def perform(client: httpx.Client):
            active = list(queries)
            findings: list[dict] = []
            seen: set[tuple[str, str, str, str]] = set()
            count = 0
            deadline = time.monotonic() + 30
            for _page in range(20):
                if time.monotonic() >= deadline:
                    raise ValueError("OSV assessment time budget exceeded")
                with client.stream(
                    "POST",
                    "https://api.osv.dev/v1/querybatch",
                    json={"queries": active},
                    headers={"Accept-Encoding": "identity"},
                    timeout=15,
                    follow_redirects=False,
                ) as response:
                    response.raise_for_status()
                    if (
                        response.headers.get("content-encoding", "identity").strip().lower()
                        != "identity"
                        or time.monotonic() >= deadline
                    ):
                        raise ValueError("OSV response encoding or time bound exceeded")
                    content = bytearray()
                    for chunk in response.iter_bytes():
                        if (
                            len(content) + len(chunk) > 4 * 1024 * 1024
                            or time.monotonic() >= deadline
                        ):
                            raise ValueError("OSV response size or time bound exceeded")
                        content.extend(chunk)
                decoded = json.loads(content)
                page = decoded.get("results") if isinstance(decoded, dict) else None
                if not isinstance(page, list) or len(page) != len(active):
                    raise ValueError("OSV result count mismatch")
                next_queries = []
                for query, item in zip(active, page, strict=True):
                    if not isinstance(item, dict) or "error" in item:
                        raise ValueError("OSV returned an incomplete assessment")
                    vulnerabilities = item.get("vulns", [])
                    if not isinstance(vulnerabilities, list) or any(
                        not isinstance(vuln, dict)
                        or not isinstance(vuln.get("id"), str)
                        or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,200}", vuln["id"])
                        for vuln in vulnerabilities
                    ):
                        raise ValueError("Invalid OSV vulnerability inventory")
                    count += len(vulnerabilities)
                    if count > 10000:
                        raise ValueError("OSV vulnerability count exceeded limit")
                    dependency = {**query["package"], "version": query["version"]}
                    for vuln in vulnerabilities:
                        key = (
                            dependency["ecosystem"],
                            dependency["name"],
                            dependency["version"],
                            vuln["id"],
                        )
                        if key not in seen:
                            seen.add(key)
                            findings.append(
                                {
                                    "scanner": "osv",
                                    "rule_id": vuln["id"],
                                    "file_path": "dependency-manifest",
                                    "line": 1,
                                    "severity": "info",
                                    "dependency": dict(dependency),
                                }
                            )
                    token = item.get("next_page_token")
                    if token is not None:
                        if not isinstance(token, str) or not 1 <= len(token) <= 4096:
                            raise ValueError("Invalid OSV pagination token")
                        next_queries.append({**query, "page_token": token})
                active = next_queries
                if not active:
                    break
            else:
                raise ValueError("OSV pagination limit exceeded; assessment incomplete")
            return findings

        if self.client:
            return perform(self.client)
        with httpx.Client(follow_redirects=False) as client:
            return perform(client)
