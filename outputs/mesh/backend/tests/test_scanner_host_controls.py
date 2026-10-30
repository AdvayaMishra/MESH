import json
from types import SimpleNamespace

import pytest
from app.scanning import DockerSandbox, validate_docker_host

VALID = {
    "os": "linux",
    "arch": "x86_64",
    "memory": True,
    "swap": True,
    "cpu": True,
    "period": True,
    "pids": True,
    "security": ["name=seccomp,profile=builtin"],
}


@pytest.mark.parametrize("field", ["memory", "swap", "cpu", "period", "pids"])
@pytest.mark.parametrize("value", [False, None, "true"])
def test_unsupported_or_ambiguous_resource_controls_are_rejected(field, value):
    with pytest.raises(ValueError):
        validate_docker_host({**VALID, field: value})


@pytest.mark.parametrize(
    "change",
    [
        {"os": "windows"},
        {"arch": "arm64"},
        {"security": []},
        {"security": ["name=seccomp,profile=unconfined"]},
    ],
)
def test_wrong_platform_or_missing_seccomp_cannot_scan(change):
    with pytest.raises(ValueError):
        validate_docker_host({**VALID, **change})


def api_response(capabilities):
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
    return json.dumps({key: capabilities.get(name) for name, key in keys.items()}).encode()


def test_host_probe_is_cached_only_after_verified_success(monkeypatch):
    calls = []

    def run(command, **kwargs):
        calls.append(command)
        return SimpleNamespace(stdout=api_response(VALID))

    monkeypatch.setattr("app.scanning.subprocess.run", run)
    sandbox = DockerSandbox()
    sandbox.verify_host()
    sandbox.verify_host()
    assert len(calls) == 1 and calls[0][1] == "info"


def test_scanner_process_never_starts_when_host_checks_fail(monkeypatch):
    monkeypatch.setattr(
        "app.scanning.subprocess.run",
        lambda *args, **kwargs: SimpleNamespace(stdout=api_response({**VALID, "swap": False})),
    )

    def forbidden(*args, **kwargs):
        raise AssertionError("Scanner started on unsupported host")

    monkeypatch.setattr("app.scanning.subprocess.Popen", forbidden)
    with pytest.raises(RuntimeError, match="resource controls"):
        DockerSandbox().execute("mesh-12345", "bandit")
