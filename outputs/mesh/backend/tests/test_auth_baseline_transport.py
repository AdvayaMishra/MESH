import importlib.util
import json
from pathlib import Path

import httpx
import pytest


def driver():
    path = Path(__file__).resolve().parents[2] / "scripts/configure_supabase_auth_baseline.py"
    spec = importlib.util.spec_from_file_location("mesh_auth_baseline_driver", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_settings_only_defers_all_email_customizations(tmp_path):
    state = initial()
    patches = []

    def handler(request):
        if request.method == "PATCH":
            patch = json.loads(request.content)
            patches.append(patch)
            assert all(
                not key.startswith(("mailer_subjects_", "mailer_templates_")) for key in patch
            )
            state.update(patch)
        return httpx.Response(200, json=state)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = driver().configure(
            "abcdefghijklmnopqrst",
            "private-token",
            client,
            tmp_path / "rollback.json",
            apply=True,
            settings_only=True,
        )
    assert result["status"] == "applied_and_verified"
    assert len(patches) == 1
    assert len(result["deferred_email_fields"]) == 4


def initial():
    return {
        "password_min_length": 6,
        "mailer_otp_length": 8,
        "smtp_max_frequency": 60,
        "mailer_otp_exp": 3600,
        "jwt_exp": 3600,
        "security_refresh_token_reuse_interval": 10,
        "smtp_pass": "private-password",
        "security_captcha_secret": "private-captcha-secret",
    }


def test_real_configuration_protocol_only_patches_selected_fields_and_verifies_readback(tmp_path):
    state = initial()
    methods = []

    def handler(request):
        methods.append(request.method)
        assert (
            str(request.url)
            == "https://api.supabase.com/v1/projects/abcdefghijklmnopqrst/config/auth"
        )
        if request.method == "PATCH":
            patch = json.loads(request.content)
            assert "smtp_pass" not in patch and "security_captcha_secret" not in patch
            state.update(patch)
        return httpx.Response(200, json=state)

    backup = tmp_path / "rollback.private.json"
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = driver().configure(
            "abcdefghijklmnopqrst", "private-token", client, backup, apply=True
        )
    assert methods == ["GET", "PATCH", "GET"]
    assert result["status"] == "applied_and_verified"
    assert result["mutations_performed"] is True
    assert result["readback_matches"] is True
    assert result["production_clearance"] is False
    assert "private" not in json.dumps(result)
    assert "private" not in backup.read_text(encoding="utf-8")
    assert (
        json.loads(backup.read_text(encoding="utf-8"))["previous_values"]["password_min_length"]
        == 6
    )


@pytest.mark.parametrize("apply", [False, True])
def test_backup_is_not_overwritten_and_dry_run_does_not_patch(tmp_path, apply):
    backup = tmp_path / "rollback.private.json"
    backup.write_text("preserved", encoding="utf-8")
    methods = []

    def handler(request):
        methods.append(request.method)
        return httpx.Response(200, json=initial())

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        if apply:
            with pytest.raises(FileExistsError):
                driver().configure(
                    "abcdefghijklmnopqrst", "private-token", client, backup, apply=True
                )
        else:
            assert (
                driver().configure("abcdefghijklmnopqrst", "private-token", client, backup)[
                    "status"
                ]
                == "planned"
            )
    assert methods == ["GET"]
    assert backup.read_text(encoding="utf-8") == "preserved"


@pytest.mark.parametrize("outcome", ["redirect", "timeout", "mismatch"])
def test_patch_failure_or_mismatch_requires_reconciliation_without_automatic_retry(
    tmp_path, outcome
):
    methods = []

    def handler(request):
        methods.append(request.method)
        if request.method == "PATCH":
            if outcome == "timeout":
                raise httpx.ReadTimeout("private-response", request=request)
            if outcome == "redirect":
                return httpx.Response(302, headers={"Location": "https://attacker.invalid"})
        return httpx.Response(200, json=initial())

    with httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True) as client:
        result = driver().configure(
            "abcdefghijklmnopqrst",
            "private-token",
            client,
            tmp_path / "rollback.private.json",
            apply=True,
        )
    assert result["reconciliation_required"] is True
    assert methods.count("PATCH") == 1
    assert result["mutations_performed"] is (True if outcome == "mismatch" else None)
    assert "private-response" not in json.dumps(result)
