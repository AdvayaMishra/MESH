"""Opt-in lock generation from official PyPI metadata and verified local wheels."""

import argparse
import hashlib
import json
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
PIN = re.compile(r"([a-z0-9][a-z0-9-]*)==([A-Za-z0-9.+!-]+)")


def pins(content: str) -> list[tuple[str, str]]:
    values = []
    for line in content.splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        match = PIN.fullmatch(line)
        if not match:
            raise ValueError("Only exact package pins are supported")
        values.append((match[1], match[2]))
    if not values or len(values) != len({name for name, _ in values}):
        raise ValueError("Empty or duplicate package pins")
    return values


def release_wheels(data: dict, name: str, version: str) -> dict[str, str]:
    def canonical(value):
        return re.sub(r"[-_.]+", "-", value).lower()

    if canonical(data["info"]["name"]) != canonical(name) or data["info"]["version"] != version:
        raise ValueError("PyPI release identity mismatch")
    artifacts = {}
    for artifact in data["urls"]:
        if artifact.get("packagetype") != "bdist_wheel" or artifact.get("yanked"):
            continue
        filename, digest = artifact["filename"], artifact["digests"]["sha256"]
        if (
            Path(filename).name != filename
            or not filename.endswith(".whl")
            or not re.fullmatch(r"[a-f0-9]{64}", digest)
        ):
            raise ValueError("Invalid published wheel metadata")
        if filename in artifacts and artifacts[filename] != digest:
            raise ValueError("Conflicting artifact digests")
        artifacts[filename] = digest
    if not artifacts:
        raise ValueError("No non-yanked published wheels")
    return artifacts


def generate(cache: Path, allow: bool) -> dict:
    if not allow or not cache.is_absolute() or not cache.is_dir():
        raise ValueError("Explicit PyPI metadata opt-in and absolute wheel cache required")
    runtime = pins((ROOT / "requirements.lock").read_text(encoding="utf-8"))
    build = [("setuptools", "80.9.0"), ("wheel", "0.45.1"), ("packaging", "26.3")]
    cached = {path.name: path for path in cache.glob("*.whl") if not path.is_symlink()}

    def fetch(item):
        name, version = item
        with httpx.Client(
            timeout=20, follow_redirects=False, headers={"Accept-Encoding": "identity"}
        ) as client:
            with client.stream("GET", f"https://pypi.org/pypi/{name}/{version}/json") as response:
                response.raise_for_status()
                if response.headers.get("content-encoding", "identity").lower() != "identity":
                    raise ValueError("Compressed release metadata unsupported")
                content = bytearray()
                for chunk in response.iter_bytes():
                    content.extend(chunk)
                    if len(content) > 4 * 1024 * 1024:
                        raise ValueError("Release metadata exceeds limit")
        artifacts = release_wheels(json.loads(content), name, version)
        matches = set(artifacts) & set(cached)
        if not matches:
            raise ValueError("No matching cached release wheel")
        for filename in matches:
            if hashlib.sha256(cached[filename].read_bytes()).hexdigest() != artifacts[filename]:
                raise ValueError("Cached wheel differs from official PyPI digest")
        return item, artifacts, len(matches)

    with ThreadPoolExecutor(max_workers=4) as executor:
        releases = dict(
            (item, (artifacts, count))
            for item, artifacts, count in executor.map(fetch, runtime + build)
        )
    outputs = {}
    for filename, required in (
        ("requirements-hashed.lock", runtime),
        ("requirements-build.lock", build),
    ):
        lines = [
            "# Official PyPI wheel SHA256 digests; regenerate with scripts/generate_dependency_hash_lock.py.",
            "--only-binary=:all:",
        ]
        for item in required:
            hashes = sorted(set(releases[item][0].values()))
            lines.append(
                "==".join(item) + " " + " ".join("--hash=sha256:" + digest for digest in hashes)
            )
        content = "\n".join(lines) + "\n"
        (ROOT / filename).write_text(content, encoding="utf-8")
        outputs[filename] = {
            "sha256": hashlib.sha256((ROOT / filename).read_bytes()).hexdigest(),
            "packages": len(required),
        }
    return {
        "passed": True,
        "verified_at_utc": datetime.now(UTC).isoformat(),
        "runtime_packages": len(runtime),
        "build_packages": len(build),
        "cached_wheels_verified": sum(count for _, count in releases.values()),
        "official_pypi_release_metadata": True,
        "sdists_allowed": False,
        "outputs": outputs,
        "limitations": [
            "Published metadata provenance and artifact integrity, not proof that packages are vulnerability-free or publisher accounts uncompromised.",
            "Binary platform compatibility is verified by separate installation/runtime checks.",
        ],
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wheel-cache", type=Path, required=True)
    parser.add_argument("--allow-public-pypi-metadata", action="store_true")
    arguments = parser.parse_args()
    try:
        report = generate(arguments.wheel_cache, arguments.allow_public_pypi_metadata)
    except Exception as error:
        print(json.dumps({"passed": False, "error_type": type(error).__name__}))
        raise SystemExit(1) from None
    (ROOT / "docs/dependency-hash-lock-results.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, indent=2))
