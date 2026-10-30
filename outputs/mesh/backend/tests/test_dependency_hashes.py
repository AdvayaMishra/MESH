import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "dependency_lock_generator", ROOT / "scripts/generate_dependency_hash_lock.py"
)
generator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(generator)


def test_hashed_runtime_lock_preserves_exact_tested_version_snapshot():
    plain = generator.pins((ROOT / "requirements.lock").read_text())
    hashed = []
    for line in (ROOT / "requirements-hashed.lock").read_text().splitlines():
        if line.startswith(("#", "--")) or not line:
            continue
        pin, *hashes = line.split()
        assert hashes and all(
            value.startswith("--hash=sha256:") and len(value) == 78 for value in hashes
        )
        hashed.extend(generator.pins(pin))
    assert hashed == plain and len(hashed) == 41
    report = json.loads((ROOT / "docs/dependency-hash-lock-results.json").read_text())
    for name, item in report["outputs"].items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == item["sha256"]


@pytest.mark.parametrize(
    "content", ["package>=1", "package==1\npackage==2", "--index-url https://untrusted.invalid", ""]
)
def test_hash_generator_rejects_unpinned_duplicate_or_redirecting_inputs(content):
    with pytest.raises(ValueError):
        generator.pins(content)


def test_release_hashes_must_match_exact_identity_and_ignore_yanked_or_source_artifacts():
    digest = "a" * 64
    artifact = {
        "packagetype": "bdist_wheel",
        "filename": "fixture-1-py3-none-any.whl",
        "digests": {"sha256": digest},
    }
    data = {
        "info": {"name": "fixture", "version": "1"},
        "urls": [
            artifact,
            {**artifact, "filename": "ignored.tar.gz", "packagetype": "sdist"},
            {**artifact, "filename": "yanked.whl", "yanked": True},
        ],
    }
    assert generator.release_wheels(data, "fixture", "1") == {artifact["filename"]: digest}
    with pytest.raises(ValueError):
        generator.release_wheels(data, "different", "1")
    data["urls"] = [{**artifact, "digests": {"sha256": "invalid"}}]
    with pytest.raises(ValueError):
        generator.release_wheels(data, "fixture", "1")


@pytest.mark.parametrize("tampered", [False, True])
def test_real_pip_enforces_artifact_hashes_without_network_or_installation(tmp_path, tampered):
    cache = tmp_path / "cache"
    cache.mkdir()
    wheel = cache / "mesh_hash_fixture-1.0-py3-none-any.whl"
    with zipfile.ZipFile(wheel, "w") as archive:
        archive.writestr(
            "mesh_hash_fixture-1.0.dist-info/METADATA",
            "Metadata-Version: 2.1\nName: mesh-hash-fixture\nVersion: 1.0\n",
        )
        archive.writestr(
            "mesh_hash_fixture-1.0.dist-info/WHEEL",
            "Wheel-Version: 1.0\nGenerator: fixture\nRoot-Is-Purelib: true\nTag: py3-none-any\n",
        )
        archive.writestr("mesh_hash_fixture-1.0.dist-info/RECORD", "")
    digest = hashlib.sha256(wheel.read_bytes()).hexdigest()
    if tampered:
        digest = "0" * 64
    lock = tmp_path / "fixture.lock"
    lock.write_text("mesh-hash-fixture==1.0 --hash=sha256:" + digest + "\n")
    destination = tmp_path / "download"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "download",
            "--no-deps",
            "--no-index",
            "--only-binary=:all:",
            "--require-hashes",
            "--find-links=" + str(cache),
            "--dest=" + str(destination),
            "-r",
            str(lock),
        ],
        capture_output=True,
        timeout=30,
        env={**os.environ, "PIP_DISABLE_PIP_VERSION_CHECK": "1"},
    )
    assert (result.returncode != 0) == tampered
    assert (destination / wheel.name).exists() is not tampered
