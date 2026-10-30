"""Private local worker heartbeat and cycle deadline; no remote health bypass."""

import argparse
import json
import logging
import os
import tempfile
import threading
import time
from collections.abc import Callable
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import TypedDict
from uuid import UUID, uuid4

KINDS = ("outbox", "cloud", "scan", "ocr", "retention", "billing")
MAX_CYCLE_SECONDS = {
    "outbox": 1800,
    "cloud": 300,
    "scan": 2400,
    "ocr": 600,
    "retention": 900,
    "billing": 300,
}
STALE_SECONDS = 30
MAX_IDLE_SECONDS = {
    "outbox": 15,
    "cloud": 30,
    "scan": 30,
    "ocr": 30,
    "retention": 150,
    "billing": 30,
}


class HeartbeatRecord(TypedDict):
    version: int
    kind: str
    organization_id: str
    instance_id: str
    state: str
    heartbeat_at: str | None
    cycle_started_at: str | None
    last_completed_at: str | None
    completed_cycles: int
    error_code: str | None


def instant() -> datetime:
    return datetime.now(UTC)


def location(kind: str, organization: str) -> Path:
    if kind not in KINDS:
        raise ValueError("Unknown worker kind")
    organization = str(UUID(organization))
    uid = os.getuid() if hasattr(os, "getuid") else "local"
    return Path(tempfile.gettempdir()) / f"mesh-worker-health-{uid}" / f"{kind}-{organization}.json"


class WorkerHealth:
    def __init__(
        self,
        kind: str,
        organization: str,
        *,
        path: Path | None = None,
        interval: float = 5,
        clock: Callable[[], datetime] = instant,
    ):
        self.path = path or location(kind, organization)
        if kind not in KINDS or not 0 < interval <= 10:
            raise ValueError("Invalid worker heartbeat configuration")
        self.clock, self.interval = clock, interval
        self.lock = threading.RLock()
        self.stop_event = threading.Event()
        self.thread: threading.Thread | None = None
        self.data: HeartbeatRecord = {
            "version": 1,
            "kind": kind,
            "organization_id": str(UUID(organization)),
            "instance_id": str(uuid4()),
            "state": "starting",
            "heartbeat_at": None,
            "cycle_started_at": None,
            "last_completed_at": None,
            "completed_cycles": 0,
            "error_code": None,
        }

    def publish(self) -> bool:
        temporary = None
        try:
            with self.lock:
                self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
                if self.path.parent.is_symlink() or self.path.is_symlink():
                    raise OSError("Unsafe heartbeat path")
                if hasattr(os, "getuid") and self.path.parent.stat().st_uid != os.getuid():
                    raise OSError("Heartbeat directory has another owner")
                if os.name != "nt" and self.path.parent.stat().st_mode & 0o077:
                    raise OSError("Heartbeat directory is not private")
                self.data["heartbeat_at"] = self.clock().isoformat()
                with tempfile.NamedTemporaryFile(
                    mode="w",
                    encoding="utf-8",
                    prefix=".mesh-heartbeat-",
                    dir=self.path.parent,
                    delete=False,
                ) as stream:
                    temporary = Path(stream.name)
                    json.dump(self.data, stream)
                os.replace(temporary, self.path)
            return True
        except (OSError, ValueError) as error:
            logging.getLogger("mesh").warning(
                "worker_health_write_failed", extra={"exception_type": type(error).__name__}
            )
            return False
        finally:
            if temporary is not None:
                try:
                    temporary.unlink(missing_ok=True)
                except OSError:
                    logging.getLogger("mesh").warning("worker_health_temporary_cleanup_failed")

    def pulse(self):
        while not self.stop_event.wait(self.interval):
            self.publish()

    def __enter__(self):
        self.publish()
        self.thread = threading.Thread(target=self.pulse, name="mesh-worker-heartbeat", daemon=True)
        self.thread.start()
        return self

    @contextmanager
    def cycle(self):
        with self.lock:
            self.data["state"] = "running"
            self.data["cycle_started_at"] = self.clock().isoformat()
            self.data["error_code"] = None
            self.publish()
        try:
            yield
        except BaseException:
            with self.lock:
                self.data["state"] = "error"
                self.data["error_code"] = "cycle_failed"
                self.publish()
            raise
        else:
            with self.lock:
                self.data["completed_cycles"] += 1
                self.data["state"] = "idle"
                self.data["cycle_started_at"] = None
                self.data["last_completed_at"] = self.clock().isoformat()
                self.publish()

    def __exit__(self, exc_type, exc, traceback):
        self.stop_event.set()
        if self.thread is not None:
            self.thread.join(timeout=2)
        with self.lock:
            self.data["state"] = "error" if exc_type else "stopped"
            self.data["error_code"] = "cycle_failed" if exc_type else None
            self.publish()


def check(
    kind: str,
    organization: str,
    *,
    path: Path | None = None,
    clock: Callable[[], datetime] = instant,
) -> dict:
    try:
        organization = str(UUID(organization))
        path = path or location(kind, organization)
        if kind not in KINDS or path.is_symlink():
            raise ValueError("Invalid health binding")
        with path.open(encoding="utf-8") as stream:
            raw = stream.read(8193)
        if len(raw.encode()) > 8192:
            raise ValueError("Invalid health record size")
        data = json.loads(raw)
        if set(data) != {
            "version",
            "kind",
            "organization_id",
            "instance_id",
            "state",
            "heartbeat_at",
            "cycle_started_at",
            "last_completed_at",
            "completed_cycles",
            "error_code",
        }:
            raise ValueError("Invalid health record shape")
        if data["version"] != 1 or data["kind"] != kind or data["organization_id"] != organization:
            raise ValueError("Worker health binding mismatch")
        if not isinstance(data["instance_id"], str) or type(data["version"]) is not int:
            raise ValueError("Invalid health identity")
        UUID(data["instance_id"])
        if data["state"] not in {"starting", "running", "idle", "stopped", "error"} or data[
            "error_code"
        ] not in {None, "cycle_failed"}:
            raise ValueError("Invalid health state")
        if type(data["completed_cycles"]) is not int or data["completed_cycles"] < 0:
            raise ValueError("Invalid worker cycle counter")
        current = clock()

        def age(value):
            timestamp = datetime.fromisoformat(value)
            if timestamp.tzinfo is None:
                raise ValueError("Timezone required")
            return (current - timestamp).total_seconds()

        elapsed = age(data["heartbeat_at"])
        reason = "ok"
        if elapsed < -5 or elapsed > STALE_SECONDS:
            reason = "stale_or_clock_invalid"
        elif data["state"] not in {"idle", "running"}:
            reason = "not_running"
        elif (
            data["state"] == "running"
            and not -5 <= age(data["cycle_started_at"]) <= MAX_CYCLE_SECONDS[kind]
        ):
            reason = "cycle_overdue"
        elif data["state"] == "idle" and (
            data["completed_cycles"] == 0 or data["last_completed_at"] is None
        ):
            reason = "no_completed_cycle"
        elif (
            data["state"] == "idle"
            and not -5 <= age(data["last_completed_at"]) <= MAX_IDLE_SECONDS[kind]
        ):
            reason = "cycle_overdue"
        return {
            "healthy": reason == "ok",
            "reason": reason,
            "kind": kind,
            "state": data["state"],
            "completed_cycles": data["completed_cycles"],
        }
    except (OSError, ValueError, TypeError, KeyError, OverflowError, RecursionError):
        return {"healthy": False, "reason": "missing_or_invalid", "kind": kind}


def run_loop(
    kind: str,
    organization: str,
    action: Callable[[], object],
    *,
    repeat: bool,
    interval: float,
    idle_only: bool = False,
):
    from app.core.logging import configure

    logger = configure()
    try:
        with WorkerHealth(kind, organization) as health:
            while True:
                with health.cycle():
                    result = action()
                if not repeat:
                    return
                if not idle_only or not result:
                    time.sleep(interval)
    except KeyboardInterrupt:
        raise SystemExit(130) from None
    except Exception as error:
        logger.error(
            "worker_loop_failed",
            extra={"exception_type": type(error).__name__, "worker_kind": kind},
        )
        raise SystemExit(1) from None


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kind", choices=KINDS, required=True)
    parser.add_argument("--organization", type=UUID, required=True)
    parser.add_argument("--file", type=Path)
    args = parser.parse_args()
    result = check(args.kind, str(args.organization), path=args.file)
    print(json.dumps(result))
    raise SystemExit(0 if result["healthy"] else 1)
