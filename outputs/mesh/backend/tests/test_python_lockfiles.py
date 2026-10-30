import importlib.util
import json
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "mesh_python_locks", Path(__file__).resolve().parents[2] / "security-engine/dependencies.py"
)
parser = importlib.util.module_from_spec(spec)
spec.loader.exec_module(parser)


def test_pipenv_includes_custom_categories_and_ignores_marker_evaluation(tmp_path):
    (tmp_path / "Pipfile.lock").write_text(
        json.dumps(
            {
                "_meta": {},
                "default": {
                    "example_pkg": {"version": "==1.2", "markers": "sys_platform == 'none'"}
                },
                "develop": {},
                "security": {"other": {"version": "==2.3"}},
            }
        )
    )
    assert parser.extract(tmp_path) == [
        {"ecosystem": "PyPI", "name": "example-pkg", "version": "1.2"},
        {"ecosystem": "PyPI", "name": "other", "version": "2.3"},
    ]


@pytest.mark.parametrize(
    "entry",
    [
        {"git": "https://example.invalid/private"},
        {"version": ">=1"},
        {"path": "../private"},
        {"version": "==1", "editable": True},
    ],
)
def test_pipenv_unsupported_sources_fail_closed(tmp_path, entry):
    (tmp_path / "Pipfile.lock").write_text(json.dumps({"default": {"thing": entry}, "develop": {}}))
    with pytest.raises(ValueError):
        parser.extract(tmp_path)


@pytest.mark.parametrize(
    "name,header,source",
    [
        ("uv.lock", "version = 1", 'source = { registry = "https://pypi.org/simple" }'),
        ("poetry.lock", '[metadata]\nlock-version = "2.1"', ""),
    ],
)
def test_toml_lockfiles_extract_pinned_registry_packages(tmp_path, name, header, source):
    (tmp_path / name).write_text(
        header + '\n[[package]]\nname="Example_pkg"\nversion="1.2.3"\n' + source
    )
    assert parser.extract(tmp_path) == [
        {"ecosystem": "PyPI", "name": "example-pkg", "version": "1.2.3"}
    ]


@pytest.mark.parametrize(
    "source", ['{ git = "https://example.invalid/private" }', "{ registry = 1 }", "{}"]
)
def test_uv_unknown_sources_fail_instead_of_clean_scan(tmp_path, source):
    (tmp_path / "uv.lock").write_text(
        'version=1\n[[package]]\nname="thing"\nversion="1"\nsource=' + source
    )
    with pytest.raises(ValueError):
        parser.extract(tmp_path)


def test_uv_root_is_skipped_but_all_platform_versions_are_included(tmp_path):
    (tmp_path / "uv.lock").write_text(
        'version=1\n[[package]]\nname="root"\nversion="1"\nsource={virtual="."}\n'
        + "".join(
            '[[package]]\nname="thing"\nversion="'
            + version
            + '"\nsource={registry="https://pypi.org/simple"}\n'
            for version in ["1", "2"]
        )
    )
    assert {p["version"] for p in parser.extract(tmp_path)} == {"1", "2"}


def test_future_uv_version_fails_explicitly(tmp_path):
    (tmp_path / "uv.lock").write_text("version=9\npackage=[]")
    with pytest.raises(ValueError, match="version"):
        parser.extract(tmp_path)
