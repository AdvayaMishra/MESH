import importlib.util
import json
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "mesh_cdx", Path(__file__).resolve().parents[2] / "security-engine/dependencies.py"
)
parser = importlib.util.module_from_spec(spec)
spec.loader.exec_module(parser)


def write(root, components, version="1.6"):
    (root / "fixture.cdx.json").write_text(
        json.dumps({"bomFormat": "CycloneDX", "specVersion": version, "components": components})
    )


def test_cyclonedx_nested_purls_are_static_deduplicated_and_do_not_emit_urls(tmp_path):
    write(
        tmp_path,
        [
            {
                "purl": "pkg:pypi/Django@1.2?repository_url=https://private.invalid/token",
                "version": "1.2",
                "components": [{"purl": "pkg:npm/%40scope/tool@2.3", "version": "2.3"}],
            }
        ],
    )
    result = parser.extract(tmp_path)
    assert result == [
        {"ecosystem": "PyPI", "name": "django", "version": "1.2"},
        {"ecosystem": "npm", "name": "@scope/tool", "version": "2.3"},
    ]
    assert "private" not in json.dumps(result)


@pytest.mark.parametrize(
    "component",
    [
        {"purl": "pkg:maven/group/name@1", "version": "1"},
        {"purl": "pkg:pypi/thing", "version": "1"},
        {"purl": "pkg:pypi/thing@1", "version": "2"},
        {"purl": "pkg:pypi/../thing@1", "version": "1"},
        {"purl": "https://private.invalid/token", "version": "1"},
        {"version": "1"},
    ],
)
def test_partial_or_unsupported_sbom_fails_instead_of_reporting_clean(tmp_path, component):
    write(tmp_path, [component])
    with pytest.raises(ValueError):
        parser.extract(tmp_path)


def test_cyclonedx_unknown_schema_version_is_rejected(tmp_path):
    write(tmp_path, [], version="9")
    with pytest.raises(ValueError, match="version"):
        parser.extract(tmp_path)


def test_cyclonedx_nesting_is_bounded(tmp_path):
    root = {"purl": "pkg:pypi/thing@1", "version": "1"}
    current = root
    for _ in range(34):
        child = {"purl": "pkg:pypi/thing@1", "version": "1"}
        current["components"] = [child]
        current = child
    write(tmp_path, [root])
    with pytest.raises(ValueError, match="nesting"):
        parser.extract(tmp_path)
