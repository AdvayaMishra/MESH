import copy
import importlib.util
import json
from pathlib import Path

import httpx
import pytest

spec = importlib.util.spec_from_file_location(
    "mesh_debian_security_review",
    Path(__file__).resolve().parents[2] / "scripts/review_debian_security.py",
)
reviewer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reviewer)


def finding():
    return {
        "ecosystem": "Debian:13",
        "name": "fixture",
        "version": "1:2.0-3",
        "id": "DEBIAN-CVE-2026-12345",
    }


def assessment():
    row = finding()
    return {
        "assessment_complete": True,
        "immutable_image_id": "sha256:" + "a" * 64,
        "packages": [{key: row[key] for key in ("ecosystem", "name", "version")}],
        "findings": [row],
        "vulnerability_references": 1,
    }


def tracker(record):
    return {"fixture": {"CVE-2026-12345": {"scope": "local", "releases": {"trixie": record}}}}


@pytest.mark.parametrize(
    "record,classification",
    [
        ({"status": "open", "urgency": "unimportant"}, "upstream_open"),
        ({"status": "open", "fixed_version": "9"}, "upstream_open"),
        ({"status": "resolved", "fixed_version": "0"}, "upstream_reports_not_affected"),
        (
            {"status": "resolved", "fixed_version": "2:3.0-1"},
            "upstream_fix_requires_installed_version_comparison",
        ),
        ({"status": "resolved"}, "tracker_status_requires_review"),
        ({"status": "undetermined"}, "upstream_undetermined"),
        ({"status": "new-unknown-status"}, "tracker_status_requires_review"),
        ({"status": 1}, "tracker_record_invalid"),
        ({"status": "open", "nodsa": "a" * 2001}, "tracker_record_invalid"),
    ],
)
def test_upstream_evidence_never_suppresses_or_approves_a_match(record, classification):
    source = assessment()
    before = copy.deepcopy(source)
    report = reviewer.review(source, tracker(record), {"fixture": True})
    assert report["classifications"] == {classification: 1}
    assert report["findings_retained"] == 1 and report["findings_suppressed"] == 0
    assert report["production_security_clearance"] is False
    assert report["results"][0]["review_disposition"] == "manual_review_required"
    assert report["results"][0]["runtime_exploitability"] == "not_assessed"
    assert source == before


def test_release_and_source_package_binding_cannot_use_sid_fix():
    data = {
        "fixture": {
            "CVE-2026-12345": {"releases": {"sid": {"status": "resolved", "fixed_version": "0"}}}
        }
    }
    row = reviewer.evidence(finding(), data)
    assert row["classification"] == "tracker_record_missing_or_unsupported"
    assert row["suppressed"] is False


@pytest.mark.parametrize(
    "data", [{}, {"fixture": []}, {"fixture": {"CVE-2026-12345": []}}, tracker([])]
)
def test_missing_and_malformed_tracker_records_remain_reviewable(data):
    report = reviewer.review(assessment(), data, {})
    assert report["findings_retained"] == 1
    assert report["production_security_clearance"] is False


@pytest.mark.parametrize(
    "change",
    ["incomplete", "mutable_image", "missing_count", "unbound", "duplicate", "bad_inventory"],
)
def test_incomplete_or_unbound_source_assessment_is_rejected(change):
    source = assessment()
    if change == "incomplete":
        source["assessment_complete"] = False
    elif change == "mutable_image":
        source["immutable_image_id"] = "runtime:latest"
    elif change == "missing_count":
        source["vulnerability_references"] = 0
    elif change == "unbound":
        source["findings"][0]["version"] = "other"
    elif change == "duplicate":
        source["findings"] *= 2
        source["vulnerability_references"] = 2
    else:
        source["packages"] = [{"name": []}]
    with pytest.raises(ValueError):
        reviewer.review(source, {}, {})


def test_empty_matches_never_imply_production_clearance():
    source = assessment() | {"findings": [], "vulnerability_references": 0}
    assert reviewer.review(source, {}, {})["production_security_clearance"] is False


def test_tracker_download_is_fixed_origin_and_records_decoded_hash():
    seen = []
    body = json.dumps(tracker({"status": "open"})).encode()

    def respond(request):
        seen.append(request)
        return httpx.Response(200, content=body)

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        data, provenance = reviewer.download(client)
    assert data == json.loads(body)
    assert str(seen[0].url) == reviewer.TRACKER_URL
    assert seen[0].headers["Accept-Encoding"] == "identity"
    assert provenance["decoded_bytes"] == len(body)
    assert len(provenance["decoded_sha256"]) == 64


@pytest.mark.parametrize("body", [b"{}", b"[]", b"not json"])
def test_invalid_download_fails_instead_of_empty_clean_result(body):
    with httpx.Client(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, content=body))
    ) as client:
        with pytest.raises(ValueError):
            reviewer.download(client)


def test_oversized_tracker_and_redirect_are_rejected(monkeypatch):
    monkeypatch.setattr(reviewer, "MAX_TRACKER_BYTES", 8)
    for response in [
        httpx.Response(200, content=b"x" * 9),
        httpx.Response(302, headers={"Location": "https://other.invalid"}),
    ]:
        with httpx.Client(
            transport=httpx.MockTransport(lambda _, response=response: response)
        ) as client:
            with pytest.raises((ValueError, httpx.HTTPStatusError)):
                reviewer.download(client)
