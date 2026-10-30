from collections import Counter
from threading import Lock

_lock = Lock()
_counts: Counter[tuple[str, int]] = Counter()
_duration = 0.0


def record(method: str, status: int, seconds: float) -> None:
    global _duration
    with _lock:
        _counts[
            (
                method
                if method in {"GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"}
                else "OTHER",
                status,
            )
        ] += 1
        _duration += seconds


def render() -> str:
    with _lock:
        lines = ["# TYPE mesh_http_requests_total counter"]
        lines += [
            f'mesh_http_requests_total{{method="{method}",status="{status}"}} {count}'
            for (method, status), count in sorted(_counts.items())
        ]
        lines += [
            "# TYPE mesh_http_duration_seconds_sum counter",
            f"mesh_http_duration_seconds_sum {_duration}",
        ]
        return "\n".join(lines) + "\n"
