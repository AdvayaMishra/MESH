import importlib.util
import json
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "mesh_manifest_parser", Path(__file__).resolve().parents[2] / "security-engine/dependencies.py"
)
parser = importlib.util.module_from_spec(spec)
spec.loader.exec_module(parser)


@pytest.mark.parametrize("name", ["yarn.lock", "pnpm-lock.yaml", "bun.lock", "bun.lockb"])
def test_unsupported_javascript_lockfiles_cannot_silently_report_no_dependencies(tmp_path, name):
    (tmp_path / name).write_text("unsupported fixture")
    with pytest.raises(ValueError, match="complete inventory"):
        parser.extract(tmp_path)


def test_lockfiles_hashes_markers_and_extras_are_static_and_deduplicated(tmp_path):
    (tmp_path / "requirements.lock").write_text(
        "Example_pkg[extra]==1.2.3 ; python_version > '3'\nother==4.0 \\\n --hash=sha256:1234\n",
        encoding="utf-8",
    )
    (tmp_path / "requirements-dev.txt").write_text("example-pkg==1.2.3\n", encoding="utf-8")
    assert parser.extract(tmp_path) == [
        {"ecosystem": "PyPI", "name": "example-pkg", "version": "1.2.3"},
        {"ecosystem": "PyPI", "name": "other", "version": "4.0"},
    ]


@pytest.mark.parametrize("version", [1, 2, 3])
def test_npm_transitive_and_scoped_packages(tmp_path, version):
    packages = (
        {
            "dependencies": {
                "top": {"version": "1.0.0", "dependencies": {"@scope/inner": {"version": "2.0.0"}}}
            }
        }
        if version == 1
        else {
            "packages": {
                "": {"version": "9"},
                "node_modules/top": {"version": "1.0.0"},
                "node_modules/top/node_modules/@scope/inner": {"version": "2.0.0"},
            }
        }
    )
    (tmp_path / "package-lock.json").write_text(
        json.dumps({"lockfileVersion": version, **packages})
    )
    assert {p["name"] for p in parser.extract(tmp_path)} == {"top", "@scope/inner"}


def test_npm_alias_is_audited_under_actual_registry_identity(tmp_path):
    (tmp_path / "package-lock.json").write_text(
        json.dumps(
            {
                "lockfileVersion": 3,
                "packages": {
                    "node_modules/innocent-alias": {
                        "name": "@scope/real-package",
                        "version": "1.2.3",
                    }
                },
            }
        )
    )
    assert parser.extract(tmp_path) == [
        {"ecosystem": "npm", "name": "@scope/real-package", "version": "1.2.3"}
    ]


@pytest.mark.parametrize(
    "content",
    [
        "example>=1",
        "-e git+https://example.invalid/repo",
        "thing @ https://example.invalid/private?token=secret",
    ],
)
def test_unsupported_manifest_fails_instead_of_reporting_clean(tmp_path, content):
    (tmp_path / "requirements.txt").write_text(content)
    with pytest.raises(ValueError, match="unpinned or unsupported"):
        parser.extract(tmp_path)


def test_oversized_manifest_fails_instead_of_silent_omission(tmp_path):
    (tmp_path / "requirements.lock").write_bytes(b"#" * (4 * 1024 * 1024 + 1))
    with pytest.raises(ValueError, match="limit"):
        parser.extract(tmp_path)


def test_mesh_runtime_lock_is_actually_discovered(tmp_path):
    root = Path(__file__).resolve().parents[2]
    (tmp_path / "requirements.lock").write_bytes((root / "requirements.lock").read_bytes())
    packages = parser.extract(tmp_path)
    assert len(packages) == 41
    assert any(package["name"] == "fastapi" for package in packages)


def test_hash_locked_linux_scanner_inventory_is_actually_discovered(tmp_path):
    root = Path(__file__).resolve().parents[2]
    (tmp_path / "requirements-scanner.lock").write_bytes(
        (root / "security-engine/requirements.lock").read_bytes()
    )
    packages = parser.extract(tmp_path)
    assert len(packages) == 7
    assert "bandit" in {package["name"] for package in packages}
    assert not {"semgrep", "mcp", "opentelemetry-api"} & {package["name"] for package in packages}


def test_historical_hash_snapshot_remains_parseable_without_installation(tmp_path):
    root = Path(__file__).resolve().parents[2]
    (tmp_path / "requirements.lock").write_bytes(
        (root / "security-engine/legacy-full-cli.snapshot").read_bytes()
    )
    assert len(parser.extract(tmp_path)) == 69


@pytest.mark.parametrize(
    "reference", ["../../outside.txt", "missing.txt", "https://example.invalid/private", "other.in"]
)
def test_manifest_references_cannot_escape_or_silently_skip(tmp_path, reference):
    (tmp_path / "requirements.txt").write_text("-r " + reference)
    with pytest.raises(ValueError, match="reference"):
        parser.extract(tmp_path)


def test_oversized_source_cannot_be_silently_skipped_by_semgrep(tmp_path):
    (tmp_path / "a.py").write_bytes(b"#" * 1000001)
    with pytest.raises(ValueError, match="Semgrep target-size"):
        parser.assert_semgrep_source_sizes(tmp_path)


def test_large_binary_does_not_expand_claimed_semgrep_language_coverage(tmp_path):
    (tmp_path / "asset.bin").write_bytes(b"x" * 1000001)
    (tmp_path / "a.py").write_text("eval('input()')")
    parser.assert_semgrep_source_sizes(tmp_path)


def test_semgrep_staging_removes_repository_suppressions_without_changing_source(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "a.py").write_text("eval('input()') # nosemgrep\n")
    (source / ".semgrepignore").write_text("*\n")
    (source / ".git").mkdir()
    (source / ".git" / "fixture").write_text("not scanner input")
    nested = source / "nested"
    nested.mkdir()
    (nested / ".semgrepignore").write_text("*\n")
    target = tmp_path / "staged"
    parser.prepare_semgrep_tree(source, target)
    assert (source / ".semgrepignore").read_text() == "*\n"
    assert (target / ".semgrepignore").read_text() == ""
    assert (target / "nested" / ".semgrepignore").read_text() == ""
    assert (target / "a.py").read_text() == (source / "a.py").read_text()
    assert not (target / ".git").exists()


def test_semgrep_staging_rejects_copy_inside_source(tmp_path):
    with pytest.raises(ValueError, match="separate"):
        parser.prepare_semgrep_tree(tmp_path, tmp_path / "staged")


def test_semgrep_staging_checks_source_size_before_copy(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "oversized.py").write_bytes(b"#" * 1000001)
    target = tmp_path / "staged"
    with pytest.raises(ValueError, match="target-size"):
        parser.prepare_semgrep_tree(source, target)
    assert not target.exists()
