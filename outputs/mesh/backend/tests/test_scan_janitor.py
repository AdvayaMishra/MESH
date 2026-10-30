import json

import pytest
from app.scan_janitor import eligible, sweep

VOLUME = "mesh-12345678-1234-4234-8234-123456789abc"
CONTAINER = "mesh-scan-" + "a" * 32
LABELS = {
    "mesh.managed-by": "mesh-scanner",
    "mesh.temporary": "true",
    "mesh.resource": "scan",
    "mesh.created-at": "1700000000",
}


@pytest.mark.parametrize(
    "changes",
    [
        {"mesh.managed-by": "other"},
        {"mesh.temporary": "false"},
        {"mesh.created-at": "1700019900"},
        {"mesh.created-at": "not-a-date"},
        {"mesh.resource": "source"},
    ],
)
def test_janitor_never_selects_unowned_recent_or_invalid_container(changes):
    assert not eligible("container", CONTAINER, {**LABELS, **changes}, 1700020000, 7200)
    assert not eligible("container", "customer-production", LABELS, 1700020000, 7200)


def test_janitor_dry_run_and_cleanup_are_restricted_to_verified_resources():
    calls = []

    def runner(arguments):
        calls.append(arguments)
        if arguments[1] == "ls":
            return "a" * 12 if arguments[0] == "container" else VOLUME
        if arguments[1] == "inspect":
            return json.dumps(
                [
                    {"Name": "/" + CONTAINER, "Config": {"Labels": LABELS}}
                    if arguments[0] == "container"
                    else {"Name": VOLUME, "Labels": {**LABELS, "mesh.resource": "source"}}
                ]
            )
        return ""

    report = sweep(runner=runner, timestamp=1700020000)
    assert report["eligible"] == 2 and report["removed"] == 0
    assert not any(call[1] == "rm" for call in calls)
    report = sweep(apply=True, runner=runner, timestamp=1700020000)
    assert report["removed"] == 2 and report["failed"] == 0
    assert [call[0] for call in calls if call[1] == "rm"] == ["container", "volume"]


def test_janitor_failure_is_reported_without_pruning_other_resources():
    calls = []

    def runner(arguments):
        calls.append(arguments)
        if arguments[0] == "volume":
            return ""
        if arguments[1] == "ls":
            return "a" * 12
        if arguments[1] == "inspect":
            return json.dumps([{"Name": CONTAINER, "Config": {"Labels": LABELS}}])
        raise OSError("Docker failed")

    report = sweep(apply=True, runner=runner, timestamp=1700020000)
    assert report["failed"] == 1 and report["removed"] == 0
    assert all("prune" not in call for call in calls)


def test_janitor_rejects_short_cleanup_age():
    with pytest.raises(ValueError):
        sweep(minimum_age=30)


def test_stale_keeper_is_recovered_with_existing_ownership_and_age_guards():
    keeper = "mesh-keeper-" + "b" * 32
    assert eligible("container", keeper, LABELS, 1700020000, 7200)
    assert not eligible(
        "container", keeper, {**LABELS, "mesh.managed-by": "other"}, 1700020000, 7200
    )
    assert not eligible(
        "container", keeper, {**LABELS, "mesh.created-at": "1700019900"}, 1700020000, 7200
    )
    assert not eligible("container", "mesh-keeper-invalid", LABELS, 1700020000, 7200)
