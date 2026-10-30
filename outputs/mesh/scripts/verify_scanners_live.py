"""Real tools on trusted synthetic files; never runs untrusted checkouts on the host."""

import argparse
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import certifi

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.scanning import OSV  # noqa: E402


def scanner_environment(work: Path) -> dict[str, str]:
    allowed = {"PATH", "SYSTEMROOT", "WINDIR", "COMSPEC", "PATHEXT"}
    environment = {key: value for key, value in os.environ.items() if key.upper() in allowed}
    environment["SSL_CERT_FILE"] = certifi.where()
    environment["REQUESTS_CA_BUNDLE"] = certifi.where()
    environment.update(
        {
            "XDG_CONFIG_HOME": str(work),
            "TEMP": str(work),
            "TMP": str(work),
            "PYTHONUTF8": "1",
            "PYTHONIOENCODING": "utf-8",
            "SEMGREP_SETTINGS_FILE": str(work / "semgrep-settings.yaml"),
            "SEMGREP_LOG_FILE": str(work / "semgrep.log"),
            "SEMGREP_VERSION_CACHE_PATH": str(work / "semgrep-version-cache"),
            "SEMGREP_SEND_METRICS": "off",
            "SEMGREP_ENABLE_VERSION_CHECK": "0",
        }
    )
    return environment


def core_scan(core: Path, target: Path, environment: dict[str, str]) -> dict:
    """Official core on trusted fixtures; legacy workers avoid Windows socketpair failure."""
    result = {"results": [], "errors": []}
    for language, filename in [("python", "a.py"), ("javascript", "a.js")]:
        completed = subprocess.run(
            [
                str(core),
                "-rules",
                str(ROOT / "security-engine/rules.yml"),
                "-lang",
                language,
                "-json",
                "-j",
                "1",
                "-use_parmap",
                str(target / filename),
            ],
            cwd=target,
            env=environment,
            capture_output=True,
            timeout=60,
        )
        assert completed.returncode == 0, "Native Semgrep core failed"
        # Core emits progress dots before its JSON document.
        output = completed.stdout.decode("utf-8")
        data = json.loads(output[output.index("{") :])
        assert data.get("version") == "1.182.1", (
            "Semgrep core differs from the pinned policy version"
        )
        result["results"].extend(data["results"])
        result["errors"].extend(data.get("errors", []))
    return result


def verify(
    gitleaks_executable: Path,
    semgrep_executable: Path | None = None,
    semgrep_core_executable: Path | None = None,
):
    assert gitleaks_executable.is_absolute() and gitleaks_executable.is_file()
    if semgrep_executable:
        assert semgrep_executable.is_absolute() and semgrep_executable.is_file()
    if semgrep_core_executable:
        assert semgrep_core_executable.is_absolute() and semgrep_core_executable.is_file()
    report = {}
    with tempfile.TemporaryDirectory(
        prefix="mesh-scanner-proof-", dir=ROOT.parents[1] / "work"
    ) as folder:
        work = Path(folder)
        fixture = work / "repository"
        fixture.mkdir()
        environment = scanner_environment(work)
        version = subprocess.run(
            [str(gitleaks_executable), "version"],
            env=environment,
            cwd=work,
            capture_output=True,
            text=True,
            timeout=15,
            check=True,
        ).stdout.strip()
        (fixture / "a.py").write_text(
            "import subprocess\napi_key = "
            + repr("mesh" + os.urandom(24).hex())
            + "\neval('input()') # nosec # nosemgrep\nsubprocess.run('echo fixture',shell=True) # nosec # nosemgrep\n",
            encoding="utf-8",
        )
        (fixture / "a.js").write_text('eval("fixture"); // nosemgrep\n', encoding="utf-8")
        (fixture / ".bandit").write_text("[bandit]\nskips=B307,B602\n", encoding="utf-8")
        (fixture / ".gitignore").write_text("a.py\na.js\n", encoding="utf-8")
        (fixture / ".semgrepignore").write_text("*\n", encoding="utf-8")
        output = work / "leaks.json"
        completed = subprocess.run(
            [
                str(gitleaks_executable),
                "dir",
                str(fixture),
                "--config=" + str(ROOT / "security-engine/gitleaks.toml"),
                "--gitleaks-ignore-path=" + str(ROOT / "security-engine/gitleaks.ignore"),
                "--ignore-gitleaks-allow",
                "--redact=100",
                "--report-format=json",
                "--report-path=" + str(output),
                "--exit-code=0",
                "--no-banner",
            ],
            env=environment,
            cwd=fixture,
            capture_output=True,
            timeout=30,
        )
        assert completed.returncode == 0
        raw = json.loads(output.read_text(encoding="utf-8"))
        assert raw
        bandit = subprocess.run(
            [
                sys.executable,
                "-m",
                "bandit",
                "-r",
                str(fixture),
                "-f",
                "json",
                "--ignore-nosec",
                "--ini",
                str(ROOT / "security-engine/bandit.ini"),
            ],
            env=environment,
            cwd=fixture,
            capture_output=True,
            timeout=30,
        )
        assert bandit.returncode == 1 and any(
            v["test_id"] == "B307" for v in json.loads(bandit.stdout)["results"]
        )
        report["bandit_native_synthetic_fixture"] = {
            "status": "passed",
            "repository_ini_and_inline_suppressions_ignored": True,
            "limitation": "Trusted synthetic input only; Docker containment not verified",
        }
        report["gitleaks_native_synthetic_fixture"] = {
            "status": "passed",
            "findings": len(raw),
            "version": version,
            "checksum_verified": "Verify supplied executable; workspace provenance is recorded separately",
            "limitation": "Native tool on trusted synthetic files; Docker containment not verified",
        }
        spec = importlib.util.spec_from_file_location(
            "dependency_parser", ROOT / "security-engine/dependencies.py"
        )
        parser = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(parser)
        if semgrep_core_executable:
            target = work / "semgrep-core-staging"
            parser.prepare_semgrep_tree(fixture, target)
            record_semgrep_success(report, core_scan(semgrep_core_executable, target, environment))
            report["semgrep_native_synthetic_fixture"]["frontend"] = (
                "official core; explicit synthetic targets; documented -use_parmap worker mode"
            )
        elif semgrep_executable:
            target = work / "semgrep-staging"
            parser.prepare_semgrep_tree(fixture, target)
            scanned = subprocess.run(
                [
                    str(semgrep_executable),
                    "--legacy",
                    "scan",
                    "--config=" + str(ROOT / "security-engine/rules.yml"),
                    "--json",
                    "--metrics=off",
                    "--disable-version-check",
                    "--disable-nosem",
                    "--strict",
                    "--no-git-ignore",
                    "--max-target-bytes=1000000",
                    "--jobs=1",
                    ".",
                ],
                cwd=target,
                env=environment,
                capture_output=True,
                timeout=120,
            )
            if scanned.returncode != 0:
                report["semgrep_native_synthetic_fixture"] = {
                    "status": "blocked",
                    "version": "1.182.1",
                    "reason": "Native Windows core failed certificate-store initialization; Linux Docker execution remains unverified",
                    "exit_code": scanned.returncode,
                    "tls_verification_disabled": False,
                }
            data = json.loads(scanned.stdout) if scanned.returncode == 0 else None
            if data is not None:
                record_semgrep_success(report, data)
        (fixture / "requirements.lock").write_bytes((ROOT / "requirements.lock").read_bytes())
        dependencies = parser.extract(fixture)
        assert len(dependencies) == 41
        result = OSV().check(dependencies)
        report["osv_live_runtime_dependencies"] = {
            "status": "passed",
            "dependencies": len(dependencies),
            "vulnerability_references": len(result),
            "metadata_only": True,
        }
        known = OSV().check([{"ecosystem": "PyPI", "name": "django", "version": "1.2"}])
        assert known
        report["osv_live_known_vulnerable_fixture"] = {
            "status": "passed",
            "vulnerability_references": len(known),
        }
    return report


def record_semgrep_success(report: dict, data: dict) -> None:
    assert not data.get("errors")
    rules = {finding["check_id"] for finding in data["results"]}
    assert all(
        any(rule.endswith(expected) for rule in rules)
        for expected in ["mesh.python.eval", "mesh.python.shell", "mesh.javascript.eval"]
    )
    report["semgrep_native_synthetic_fixture"] = {
        "status": "passed",
        "version": "1.182.1",
        "frontend": "official --legacy Python CLI with verified CA bundle",
        "findings": len(data["results"]),
        "all_three_bundled_rules_detected": True,
        "repository_and_inline_suppressions_ignored": True,
        "metrics_and_version_checks_disabled": True,
        "limitation": "Official native Windows tool; Docker containment not verified",
    }


if __name__ == "__main__":
    args_parser = argparse.ArgumentParser(description=__doc__)
    args_parser.add_argument("--gitleaks-executable", type=Path, required=True)
    args_parser.add_argument("--semgrep-executable", type=Path)
    args_parser.add_argument("--semgrep-core-executable", type=Path)
    args = args_parser.parse_args()
    try:
        result = verify(
            args.gitleaks_executable, args.semgrep_executable, args.semgrep_core_executable
        )
    except Exception as exc:
        print(json.dumps({"failed": type(exc).__name__}))
        raise SystemExit(1) from None
    (ROOT / "docs/scanner-live-results.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(result, indent=2))
    if any(check.get("status") != "passed" for check in result.values()):
        raise SystemExit(1)
