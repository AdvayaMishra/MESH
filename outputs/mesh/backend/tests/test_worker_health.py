import json
import logging
import os
import subprocess
import sys
import time
from datetime import timedelta
from pathlib import Path

import pytest
from app.worker_health import (
    MAX_CYCLE_SECONDS,
    MAX_IDLE_SECONDS,
    WorkerHealth,
    check,
    instant,
    location,
    run_loop,
)
from conftest import ORG_A, ORG_B


@pytest.fixture(autouse=True)
def restore_application_logger():
    logger = logging.getLogger("mesh")
    handlers = list(logger.handlers)
    yield
    logger.handlers = handlers


def record(path, **overrides):
    data = {
        "version": 1,
        "kind": "outbox",
        "organization_id": ORG_A,
        "instance_id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
        "state": "idle",
        "heartbeat_at": instant().isoformat(),
        "cycle_started_at": None,
        "last_completed_at": instant().isoformat(),
        "completed_cycles": 1,
        "error_code": None,
    }
    path.write_text(json.dumps(data | overrides))


def test_worker_health_tracks_start_running_idle_and_stop_without_business_data(tmp_path):
    path = tmp_path / "health.json"
    with WorkerHealth("outbox", ORG_A, path=path, interval=0.01) as health:
        # On Windows, an open reader can temporarily deny atomic replacement.
        # Observe this in-process state machine under its lock; the separate
        # CLI/process tests exercise independent readers and fail-closed IO.
        def snapshot():
            with health.lock:
                return json.loads(path.read_text())

        def status():
            with health.lock:
                return check("outbox", ORG_A, path=path)

        assert status()["healthy"] is False
        with health.cycle():
            assert status()["healthy"] is True
            first = snapshot()["heartbeat_at"]
            deadline = time.monotonic() + 2
            while time.monotonic() < deadline and snapshot()["heartbeat_at"] == first:
                time.sleep(0.01)
            assert snapshot()["heartbeat_at"] != first
        assert status()["state"] == "idle"
        assert status()["completed_cycles"] == 1
    assert check("outbox", ORG_A, path=path)["healthy"] is False
    assert json.loads(path.read_text())["state"] == "stopped"
    if os.name != "nt":
        assert path.stat().st_mode & 0o077 == 0


def test_cycle_failure_is_recorded_without_exception_contents(tmp_path):
    path = tmp_path / "health.json"
    with (
        pytest.raises(RuntimeError),
        WorkerHealth("outbox", ORG_A, path=path) as health,
        health.cycle(),
    ):
        raise RuntimeError("private credential must not be recorded")
    assert check("outbox", ORG_A, path=path)["healthy"] is False
    assert "credential" not in path.read_text()
    assert json.loads(path.read_text())["error_code"] == "cycle_failed"


@pytest.mark.parametrize("seconds", [-31, 6])
def test_stale_or_future_heartbeat_is_unhealthy(tmp_path, seconds):
    path = tmp_path / "health.json"
    record(path, heartbeat_at=(instant() + timedelta(seconds=seconds)).isoformat())
    assert check("outbox", ORG_A, path=path)["reason"] == "stale_or_clock_invalid"


@pytest.mark.parametrize("state", ["running", "idle"])
def test_fresh_heartbeat_does_not_hide_overdue_main_cycle(tmp_path, state):
    path = tmp_path / "health.json"
    bound = MAX_CYCLE_SECONDS["outbox"] if state == "running" else MAX_IDLE_SECONDS["outbox"]
    old = (instant() - timedelta(seconds=bound + 10)).isoformat()
    record(
        path,
        state=state,
        cycle_started_at=old if state == "running" else None,
        last_completed_at=old,
    )
    assert check("outbox", ORG_A, path=path)["reason"] == "cycle_overdue"


@pytest.mark.parametrize(
    "overrides",
    [
        {"version": True},
        {"kind": "cloud"},
        {"organization_id": ORG_B},
        {"instance_id": 5},
        {"state": "private value"},
        {"error_code": "private error text"},
        {"completed_cycles": True},
        {"completed_cycles": -1},
        {"heartbeat_at": "not-a-date"},
        {"heartbeat_at": "2026-10-26T01:00:00"},
        {"state": []},
    ],
)
def test_health_checker_fails_closed_on_malformed_or_foreign_records(tmp_path, overrides):
    path = tmp_path / "health.json"
    record(path, **overrides)
    result = check("outbox", ORG_A, path=path)
    assert result["healthy"] is False and result["reason"] == "missing_or_invalid"
    assert "private" not in json.dumps(result)


def test_missing_oversized_and_non_json_records_are_unhealthy(tmp_path):
    path = tmp_path / "health.json"
    for content in (None, "not-json", "x" * 8193, "[]", "null"):
        if content is not None:
            path.write_text(content)
        assert check("outbox", ORG_A, path=path)["healthy"] is False


def test_tenant_health_paths_cannot_escape_private_namespace():
    assert location("outbox", ORG_A) != location("outbox", ORG_B)
    with pytest.raises(ValueError):
        location("../escape", ORG_A)
    with pytest.raises(ValueError):
        location("outbox", "../escape")


def test_health_write_failure_does_not_hide_job_failure_or_skip_job_work(tmp_path, monkeypatch):
    path = tmp_path / "not-a-directory"
    path.write_text("occupied")
    health = WorkerHealth("outbox", ORG_A, path=path / "health.json")
    assert health.publish() is False
    calls = []
    monkeypatch.setattr("app.worker_health.WorkerHealth", lambda *args: health)
    run_loop("outbox", ORG_A, lambda: calls.append(True), repeat=False, interval=2)
    assert calls == [True]


def test_real_health_cli_observes_live_file_and_fails_after_stop(tmp_path):
    path = tmp_path / "health.json"
    command = [
        sys.executable,
        "-m",
        "app.worker_health",
        "--kind",
        "outbox",
        "--organization",
        ORG_A,
        "--file",
        str(path),
    ]
    root = Path(__file__).resolve().parents[2]
    environment = {**os.environ, "PYTHONPATH": str(root / "backend")}
    with WorkerHealth("outbox", ORG_A, path=path) as health, health.cycle():
        live = subprocess.run(command, cwd=root, env=environment, capture_output=True, timeout=10)
        assert live.returncode == 0 and json.loads(live.stdout)["healthy"] is True
    stopped = subprocess.run(command, cwd=root, env=environment, capture_output=True, timeout=10)
    assert stopped.returncode == 1 and json.loads(stopped.stdout)["healthy"] is False


def test_worker_loop_exits_with_sanitized_structured_failure(tmp_path, monkeypatch, capsys):
    health = WorkerHealth("outbox", ORG_A, path=tmp_path / "health.json")
    monkeypatch.setattr("app.worker_health.WorkerHealth", lambda *args: health)

    def failed():
        raise RuntimeError("private password must never appear")

    with pytest.raises(SystemExit) as error:
        run_loop("outbox", ORG_A, failed, repeat=False, interval=2)
    assert error.value.code == 1
    output = capsys.readouterr().err
    assert "private" not in output and "password" not in output and "Traceback" not in output
    logged = json.loads(output.strip().splitlines()[-1])
    assert logged["exception_type"] == "RuntimeError" and logged["worker_kind"] == "outbox"
    assert check("outbox", ORG_A, path=health.path)["healthy"] is False


def test_busy_queue_preserves_immediate_drain_and_idle_backoff(tmp_path, monkeypatch):
    health = WorkerHealth("cloud", ORG_A, path=tmp_path / "health.json")
    monkeypatch.setattr("app.worker_health.WorkerHealth", lambda *args: health)
    sleeps, actions = [], []
    monkeypatch.setattr("app.worker_health.time.sleep", sleeps.append)

    def action():
        actions.append(True)
        if len(actions) == 3:
            raise KeyboardInterrupt
        return len(actions) == 1

    with pytest.raises(SystemExit) as error:
        run_loop("cloud", ORG_A, action, repeat=True, interval=5, idle_only=True)
    assert error.value.code == 130 and len(actions) == 3 and sleeps == [5]
