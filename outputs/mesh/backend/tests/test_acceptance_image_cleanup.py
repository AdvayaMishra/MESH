import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "acceptance_cleanup", ROOT / "scripts/verify_docker_runtime.py"
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_cleanup_selects_only_exact_generated_project_aliases():
    project = "mesh-test-0123456789ab"
    own = [project + "-api:latest", project + "-tests:acceptance", project + "-worker:acceptance"]
    foreign = [
        "mesh-backend:source-current",
        "postgres:16-alpine",
        "mesh-test-0123456789ac-tests:acceptance",
        project + "-tests:production",
        project + "-unrelated:latest",
        "prefix-" + project + "-api:latest",
    ]
    assert module.owned_image_tags(project, own + foreign + own) == sorted(own)


@pytest.mark.parametrize(
    "project", ["mesh", "mesh-test-*", "mesh-test-0123456789ab-extra", "production"]
)
def test_cleanup_refuses_nongenerated_project_names(project):
    with pytest.raises(ValueError):
        module.owned_image_tags(project, [project + "-api:latest"])


@pytest.mark.parametrize(
    "filename,expected",
    [
        ("pytest-9.1.1-py3-none-any.whl", True),
        ("pytest-9.0.0-py3-none-any.whl", False),
        ("other-9.1.1-py3-none-any.whl", False),
        ("pydantic_core-2.50.1-cp312-manylinux.whl", True),
    ],
)
def test_offline_cache_copies_only_exact_required_versions(filename, expected):
    assert (
        module.required_wheel(filename, {"pytest": "9.1.1", "pydantic-core": "2.50.1"}) is expected
    )


@pytest.mark.parametrize(
    "filename", ["../pytest-9.1.1-py3-none-any.whl", "pytest.whl", "pytest-9.1.1.tar.gz"]
)
def test_offline_cache_rejects_malformed_or_escaping_filenames(filename):
    with pytest.raises(ValueError):
        module.required_wheel(filename, {"pytest": "9.1.1"})
