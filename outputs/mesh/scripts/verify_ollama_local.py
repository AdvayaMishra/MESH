"""Opt-in real local Ollama inference with synthetic aggregates and disposable state.

Portable runtime must be operator-trusted. No installer, global settings, hosted
database, real identities or private records are used. Public model cache remains.
"""

import argparse
import hashlib
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from uuid import uuid4

import httpx

ROOT = Path(__file__).resolve().parents[1]
MODEL = "qwen2.5:0.5b"


def stop(process):
    if process is not None and process.poll() is None:
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=30,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        else:
            process.terminate()
        process.wait(timeout=30)


def verify(executable: Path, workspace: Path, models: Path, allow_download: bool):
    if (
        not allow_download
        or not executable.is_absolute()
        or not executable.is_file()
        or not workspace.is_absolute()
        or not models.is_absolute()
    ):
        raise ValueError(
            "Trusted absolute runtime/cache/workspace paths and model-download opt-in required"
        )
    models.mkdir(parents=True, exist_ok=True)
    with httpx.Client(timeout=30, follow_redirects=False) as client:
        manifest = client.get("https://registry.ollama.ai/v2/library/qwen2.5/manifests/0.5b")
        manifest.raise_for_status()
        expected = hashlib.sha256(manifest.content).hexdigest()
        published = manifest.headers.get(
            "Docker-Content-Digest", "sha256:" + expected
        ).removeprefix("sha256:")
        if expected != published or not re.fullmatch(r"[a-f0-9]{64}", expected):
            raise ValueError("Public model manifest digest mismatch")
    checks = {}
    process, original_cwd = None, Path.cwd()
    with tempfile.TemporaryDirectory(prefix="mesh-ollama-", dir=workspace) as directory:
        work = Path(directory)
        for name in ["profile", "appdata", "local-appdata", "temp"]:
            (work / name).mkdir()
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
        base = f"http://127.0.0.1:{port}"
        allowed = {
            "SYSTEMROOT",
            "WINDIR",
            "COMSPEC",
            "PATHEXT",
            "SystemDrive",
            "NUMBER_OF_PROCESSORS",
            "PROCESSOR_ARCHITECTURE",
            "PATH",
        }
        environment = {
            key: value
            for key, value in os.environ.items()
            if key.upper() in {name.upper() for name in allowed}
        }
        environment.update(
            OLLAMA_HOST=f"127.0.0.1:{port}",
            OLLAMA_MODELS=str(models),
            USERPROFILE=str(work / "profile"),
            APPDATA=str(work / "appdata"),
            LOCALAPPDATA=str(work / "local-appdata"),
            TEMP=str(work / "temp"),
            TMP=str(work / "temp"),
            OLLAMA_NO_CLOUD="1",
            OLLAMA_NUM_PARALLEL="1",
            OLLAMA_MAX_LOADED_MODELS="1",
            OLLAMA_CONTEXT_LENGTH="2048",
            OLLAMA_KEEP_ALIVE="5m",
            OLLAMA_VULKAN="0",
            CUDA_VISIBLE_DEVICES="-1",
            ROCR_VISIBLE_DEVICES="-1",
            GGML_VK_VISIBLE_DEVICES="-1",
        )
        log = (work / "server.log").open("w", encoding="utf-8")
        try:
            process = subprocess.Popen(
                [str(executable), "serve"],
                cwd=work,
                env=environment,
                stdout=log,
                stderr=subprocess.STDOUT,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            with httpx.Client(timeout=5, follow_redirects=False) as local:
                for _ in range(100):
                    if process.poll() is not None:
                        raise RuntimeError("Portable model server exited")
                    try:
                        version = local.get(base + "/api/version")
                        if version.status_code == 200:
                            break
                    except httpx.HTTPError:
                        pass
                    time.sleep(0.2)
                else:
                    raise RuntimeError("Local model server did not become ready")
                server_version = version.json()["version"]
                checks["actual_loopback_model_server"] = "passed"
                deadline = time.monotonic() + 900
                completed = False
                with local.stream(
                    "POST", base + "/api/pull", json={"model": MODEL, "stream": True}, timeout=90
                ) as response:
                    response.raise_for_status()
                    for line in response.iter_lines():
                        if time.monotonic() > deadline or len(line) > 16384:
                            raise ValueError("Model pull exceeded bound")
                        if not line:
                            continue
                        status = json.loads(line)
                        if status.get("error"):
                            raise RuntimeError("Public model pull failed")
                        completed = status.get("status") == "success" or completed
                if not completed:
                    raise ValueError("Public model pull was incomplete")
                entries = local.get(base + "/api/tags").json()["models"]
                loaded = next(item for item in entries if item["name"] == MODEL)
                if loaded["digest"].removeprefix("sha256:") != expected:
                    raise ValueError("Pulled model differs from the checked public manifest")
                checks["public_model_manifest_digest_verified"] = "passed"
                # Cold loading is separate from the adapter's bounded inference timeout.
                warm = local.post(
                    base + "/api/generate",
                    json={
                        "model": MODEL,
                        "prompt": "Reply OK",
                        "stream": False,
                        "options": {"num_predict": 4, "num_ctx": 2048},
                    },
                    timeout=180,
                )
                warm.raise_for_status()
                if not warm.json().get("done"):
                    raise ValueError("Model warm-up incomplete")
                os.chdir(work)
                sys.path.insert(0, str(ROOT / "backend"))
                from app.core.config import AIUsagePolicy, Settings, settings

                for field in Settings.model_fields:
                    os.environ.pop(field.upper(), None)
                os.environ.update(TEST_MODE="true", DATABASE_URL="sqlite://")
                settings.cache_clear()
                from app.ai import HTTPProvider, generate
                from app.auth import Principal
                from app.core.db import Base
                from app.models import AIUsage, Membership, Organization
                from fastapi import HTTPException
                from sqlalchemy import create_engine, event, select
                from sqlalchemy.orm import Session

                config = settings()
                config.ai_provider, config.ai_model, config.ai_url = (
                    "ollama",
                    MODEL,
                    base + "/api/chat",
                )
                org, user = str(uuid4()), str(uuid4())
                config.ai_policies = {
                    org: AIUsagePolicy(provider="ollama", model=MODEL, monthly_requests=1)
                }
                engine = create_engine("sqlite://")

                @event.listens_for(engine, "connect")
                def foreign_keys(connection, _):
                    connection.execute("PRAGMA foreign_keys=ON")

                Base.metadata.create_all(engine)
                with Session(engine) as db:
                    db.add(Organization(id=org, name="Synthetic local inference fixture"))
                    db.flush()
                    db.add(
                        Membership(
                            organization_id=org,
                            user_id=user,
                            email="fixture@example.invalid",
                            role="hr",
                        )
                    )
                    db.commit()
                    actor = Principal(user, org, "hr")
                    result = generate(db, actor, "hr", {"employees": 2, "awaiting_verification": 1})
                    assert result["provider"] == "ollama"
                    assert result["summary"] and result["limitations"]
                    assert (
                        result["usage"]["input_units"] > 0 and result["usage"]["output_units"] > 0
                    )
                    db.commit()
                    usage = db.scalar(select(AIUsage))
                    assert usage.provider == "ollama" and usage.model == MODEL
                    counters = {
                        "input_units": usage.input_units,
                        "output_units": usage.output_units,
                    }
                    checks["real_inference_structured_schema_and_usage_persisted"] = "passed"
                    try:
                        generate(db, actor, "hr", {"employees": 2})
                    except HTTPException as error:
                        assert error.status_code == 429
                    else:
                        raise AssertionError("Tenant request budget was bypassed")
                    checks["actual_usage_denies_next_request_before_dispatch"] = "passed"
                engine.dispose()
                ps = local.get(base + "/api/ps").json()["models"]
                assert ps and all(item.get("size_vram", 0) == 0 for item in ps)
                checks["cpu_only_inference"] = "passed"
                stop(process)
                try:
                    HTTPProvider().generate("hr", {"employees": 2})
                except HTTPException as error:
                    assert error.status_code == 503
                else:
                    raise AssertionError("Stopped model provider reported success")
                checks["provider_outage_fails_closed"] = "passed"
        finally:
            stop(process)
            log.close()
            shutil.copyfile(work / "server.log", workspace / "ollama-last-server.log")
            os.chdir(original_cwd)
    checks["owned_process_profile_and_synthetic_database_removed"] = "passed"
    return {
        "passed": True,
        "checks": checks,
        "runtime_version": server_version,
        "model": MODEL,
        "model_manifest_sha256": expected,
        "usage": counters,
        "limitations": [
            "Actual local CPU model/schema/usage acceptance with fictional aggregate counts only; no private records or hosted identity/database.",
            "Does not validate model accuracy, production throughput, cloud providers, invoices or hard spending caps.",
            "Public model/runtime cache retained under the workspace; no installer, Windows service or global environment change.",
        ],
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ollama-executable", type=Path, required=True)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--models", type=Path, required=True)
    parser.add_argument("--allow-model-download", action="store_true")
    args = parser.parse_args()
    try:
        report = verify(
            args.ollama_executable, args.workspace, args.models, args.allow_model_download
        )
    except Exception as error:
        report = {"passed": False, "error_type": type(error).__name__}
    (ROOT / "docs/ollama-live-results.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, indent=2))
    raise SystemExit(0 if report["passed"] else 1)
