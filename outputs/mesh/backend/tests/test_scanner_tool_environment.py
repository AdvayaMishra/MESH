import importlib.util
from pathlib import Path


def test_native_tool_verifier_never_inherits_backend_credentials(monkeypatch, tmp_path):
    source = Path(__file__).resolve().parents[2] / "scripts/verify_scanners_live.py"
    spec = importlib.util.spec_from_file_location("mesh_scanner_verifier", source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    for name in (
        "DATABASE_URL",
        "SUPABASE_STORAGE_KEY",
        "AWS_SECRET_ACCESS_KEY",
        "GITHUB_PRIVATE_KEY",
        "SEMGREP_APP_TOKEN",
    ):
        monkeypatch.setenv(name, "DO_NOT_FORWARD_FIXTURE")
    environment = module.scanner_environment(tmp_path)
    assert "DO_NOT_FORWARD_FIXTURE" not in environment.values()
    assert environment["SEMGREP_SETTINGS_FILE"].startswith(str(tmp_path))
    assert environment["SEMGREP_SEND_METRICS"] == "off"
    assert environment["SEMGREP_ENABLE_VERSION_CHECK"] == "0"
