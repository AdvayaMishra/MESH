import importlib.util
import json
import sys
from pathlib import Path

import httpx
import pytest


@pytest.fixture
def operator(monkeypatch):
    scripts = Path(__file__).resolve().parents[2] / "scripts"
    monkeypatch.syspath_prepend(str(scripts))
    spec = importlib.util.spec_from_file_location(
        "mesh_turnstile_operator", scripts / "configure_supabase_turnstile.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_patch_is_narrow_and_rollback_exclusive(operator, tmp_path):
    state = {
        "security_captcha_enabled": False,
        "security_captcha_provider": "hcaptcha",
        "security_captcha_secret": "prior-private-value",
        "site_url": "http://localhost:3000",
    }
    writes = []

    def handle(request):
        if request.method == "PATCH":
            patch = json.loads(request.content)
            writes.append(patch)
            state.update(patch)
        return httpx.Response(200, json=state)

    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        report = operator.configure(
            client,
            "a" * 20,
            "new-private-value-123456",
            tmp_path / "rollback.private.json",
            apply=True,
        )
    assert report["readback_matches"] is True
    assert set(writes[0]) == {
        "security_captcha_enabled",
        "security_captcha_provider",
        "security_captcha_secret",
    }
    assert "private-value" not in json.dumps(report)
    rollback = json.loads((tmp_path / "rollback.private.json").read_text())
    assert rollback["previous_values"]["security_captcha_secret"] == "prior-private-value"
    assert state["site_url"] == "http://localhost:3000"


def test_plan_never_mutates(operator, tmp_path):
    def handle(request):
        assert request.method == "GET"
        return httpx.Response(200, json={"security_captcha_enabled": False})

    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        report = operator.configure(
            client, "a" * 20, "new-private-value-123456", tmp_path / "rollback"
        )
    assert report["status"] == "planned"
    assert not (tmp_path / "rollback").exists()


def test_refuses_replacing_enabled_provider(operator, tmp_path):
    with httpx.Client(
        transport=httpx.MockTransport(
            lambda r: httpx.Response(200, json={"security_captcha_enabled": True})
        )
    ) as client:
        with pytest.raises(ValueError, match="already enabled"):
            operator.configure(
                client, "a" * 20, "new-private-value-123456", tmp_path / "rollback", apply=True
            )


def test_ambiguous_patch_is_not_retried(operator, tmp_path):
    calls = []

    def handle(request):
        calls.append(request.method)
        if request.method == "PATCH":
            raise httpx.ReadTimeout("private-provider-message", request=request)
        return httpx.Response(200, json={"security_captcha_enabled": False})

    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        report = operator.configure(
            client, "a" * 20, "new-private-value-123456", tmp_path / "rollback", apply=True
        )
    assert calls == ["GET", "PATCH"]
    assert report["mutations_performed"] is None
    assert "private-provider-message" not in json.dumps(report)


def test_existing_rollback_blocks_patch(operator, tmp_path):
    path = tmp_path / "rollback"
    path.write_text("preserve")

    def handle(request):
        assert request.method == "GET"
        return httpx.Response(200, json={"security_captcha_enabled": False})

    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        with pytest.raises(FileExistsError):
            operator.configure(client, "a" * 20, "new-private-value-123456", path, apply=True)
    assert path.read_text() == "preserve"
