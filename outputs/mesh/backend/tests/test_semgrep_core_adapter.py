import importlib.util
import json
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest

ENGINE = Path(__file__).resolve().parents[2] / "security-engine"


@pytest.fixture
def engine(monkeypatch):
    monkeypatch.syspath_prepend(str(ENGINE))
    spec = importlib.util.spec_from_file_location("mesh_core_adapter", ENGINE / "semgrep_core.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_explicit_targets_cover_bundled_languages_and_preserve_paths(engine, tmp_path):
    for name in ["space ' quote.py", "a.js", "a.ts", "a.tsx", "a.txt", ".semgrepignore"]:
        (tmp_path / name).write_text("eval('input')")
    manifest = engine.target_manifest(tmp_path)
    assert manifest[0] == "Targets"
    assert len(manifest[1]) == 4
    assert {item[1]["analyzer"] for item in manifest[1]} == {"python", "javascript", "typescript"}
    assert any(item[1]["path"]["ppath"] == "/space ' quote.py" for item in manifest[1])
    assert all(item[1]["products"] == ["sast"] for item in manifest[1])


@pytest.mark.parametrize(
    "change",
    [
        {"version": "other"},
        {"errors": None},
        {"errors": [{"message": "partial"}]},
        {"skipped_targets": [{"path": "a.py"}]},
        {"results": None},
        {"results": [{"check_id": "unexpected"}]},
        {"results": [{}] * 20001},
    ],
)
def test_partial_or_unexpected_core_results_fail_closed(engine, change):
    report = {"version": engine.VERSION, "errors": [], "results": []} | change
    with pytest.raises(ValueError):
        engine.validate_report(report, {"mesh.python.eval"})


def test_core_manifest_scan_retains_suppressed_finding(engine, tmp_path, monkeypatch):
    source = tmp_path / "repo"
    source.mkdir()
    (source / "a.py").write_text("eval('input()') # nosemgrep\n")
    (source / ".semgrepignore").write_text("*\n")
    policy = tmp_path / "rules.yml"
    policy.write_text(json.dumps({"rules": [{"id": "mesh.python.eval", "languages": ["python"]}]}))
    report = {
        "version": engine.VERSION,
        "errors": [],
        "results": [{"check_id": "mesh.python.eval", "extra": {"is_ignored": True}}],
    }

    def run(command, **kwargs):
        manifest_path = Path(command[command.index("-targets") + 1])
        manifest = json.loads(manifest_path.read_text())
        assert len(manifest[1]) == 1
        assert command[0] == str(tmp_path / "trusted-core")
        assert not (tmp_path / "scan" / ".semgrepignore").read_text()
        kwargs["stdout"].write(b".." + json.dumps(report).encode())
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(engine.subprocess, "run", run)
    assert engine.scan(source, tmp_path / "scan", tmp_path / "trusted-core", policy) == report
    assert (source / ".semgrepignore").read_text() == "*\n"


def test_native_wheel_extraction_excludes_python_frontend(tmp_path):
    spec = importlib.util.spec_from_file_location(
        "mesh_core_extract", ENGINE / "extract_semgrep_core.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    wheel = tmp_path / "fixture.whl"
    prefix = "semgrep-1.182.1.data/purelib/semgrep/bin/"
    with zipfile.ZipFile(wheel, "w") as archive:
        archive.writestr(prefix + "semgrep-core", b"trusted fixture binary")
        archive.writestr(prefix + "libs/libexample.so", b"fixture library")
        archive.writestr(prefix + "__init__.py", "raise Exception('never import')")
        archive.writestr("mcp/server.py", "raise Exception('never import')")
    destination = tmp_path / "native"
    module.extract(wheel, destination)
    assert (destination / "semgrep-core").read_bytes() == b"trusted fixture binary"
    assert (destination / "libs/libexample.so").read_bytes() == b"fixture library"
    assert not (destination / "__init__.py").exists()
    assert not (destination / "mcp").exists()


@pytest.mark.parametrize("entry", ["../escape", "unrelated-file"])
def test_native_extraction_rejects_traversal_or_missing_binary(tmp_path, entry):
    spec = importlib.util.spec_from_file_location(
        "mesh_core_extract_bad", ENGINE / "extract_semgrep_core.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    wheel = tmp_path / "invalid.whl"
    with zipfile.ZipFile(wheel, "w") as archive:
        archive.writestr("semgrep-1.182.1.data/purelib/semgrep/bin/" + entry, "fixture")
    with pytest.raises(ValueError):
        module.extract(wheel, tmp_path / "native")
    assert not (tmp_path / "escape").exists()
