"""Bounded loopback HTTP concurrency smoke; never a production load benchmark."""

import argparse
import json
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from statistics import median
from uuid import UUID

import httpx


def verify(approved: bool):
    if not approved:
        raise ValueError("Explicit disposable local-service opt-in required")
    targets = (
        [("/health/live", 200)] * 64
        + [("/health/ready", 200)] * 32
        + [("/api/v1/users/me/sessions", 401)] * 32
    )
    start = time.monotonic()
    with httpx.Client(
        base_url="http://127.0.0.1:8000",
        timeout=5,
        trust_env=False,
        limits=httpx.Limits(max_connections=4, max_keepalive_connections=4),
    ) as client:

        def probe(target):
            path, expected = target
            began = time.monotonic()
            response = client.get(path)
            identity = str(UUID(response.headers["x-request-id"]))
            assert (
                response.status_code == expected and response.headers["cache-control"] == "no-store"
            )
            assert response.headers["x-content-type-options"] == "nosniff"
            return response.status_code, identity, (time.monotonic() - began) * 1000

        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(probe, targets))
    assert len({item[1] for item in results}) == len(targets)
    durations = sorted(item[2] for item in results)
    return {
        "passed": True,
        "requests": len(results),
        "concurrency": 4,
        "status_counts": dict(Counter(str(item[0]) for item in results)),
        "elapsed_seconds": round(time.monotonic() - start, 3),
        "latency_ms": {
            "median": round(median(durations), 2),
            "p95": round(durations[int(len(durations) * 0.95) - 1], 2),
            "maximum": round(max(durations), 2),
        },
        "unique_request_ids_and_security_headers": True,
        "limitations": [
            "128 requests/four concurrent workers against the disposable loopback Compose API only.",
            "Health/readiness and anonymous denial only; no authenticated business load, provider Auth, endurance or production capacity claim.",
            "No hosted records, credentials or external services used.",
        ],
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--disposable-local-service", action="store_true")
    args = parser.parse_args()
    try:
        report = verify(args.disposable_local_service)
    except Exception as error:
        report = {"passed": False, "error_type": type(error).__name__}
    print(json.dumps(report))
    raise SystemExit(0 if report["passed"] else 1)
