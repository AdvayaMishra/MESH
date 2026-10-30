import importlib.util
from pathlib import Path

import httpx
import pytest

spec = importlib.util.spec_from_file_location(
    "mesh_image_os_audit", Path(__file__).resolve().parents[2] / "scripts/audit_debian_image.py"
)
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


def test_debian_inventory_uses_source_identity_version_epochs_and_installed_status():
    inventory = audit.packages(
        {
            "release": {"ID": "debian", "VERSION_ID": '"13"'},
            "status": """
Package: shared-library
Source: source-library (1:2.0-3)
Version: 1:2.0-3+b1
Status: install ok installed

Package: shared-library-dev
Source: source-library (1:2.0-3)
Version: 1:2.0-3+b1
Status: install ok installed

Package: removed
Version: 1
Status: deinstall ok config-files
""",
        }
    )
    assert inventory == [{"ecosystem": "Debian:13", "name": "source-library", "version": "1:2.0-3"}]


@pytest.mark.parametrize(
    "release,status",
    [
        ({"ID": "alpine", "VERSION_ID": "3.24"}, ""),
        ({"ID": "debian", "VERSION_ID": "unstable"}, ""),
        ({"ID": "debian", "VERSION_ID": "13"}, ""),
        (
            {"ID": "debian", "VERSION_ID": "13"},
            "Package: ../invalid\nVersion: 1\nStatus: install ok installed",
        ),
        (
            {"ID": "debian", "VERSION_ID": "13"},
            "Package: valid\nVersion: 1 invalid\nStatus: install ok installed",
        ),
    ],
)
def test_invalid_or_empty_os_inventory_fails_instead_of_clean(release, status):
    with pytest.raises(ValueError):
        audit.packages({"release": release, "status": status})


def test_osv_pagination_retains_exact_package_binding_and_deduplicates():
    calls = []

    def respond(request):
        import json

        payload = json.loads(request.content)
        calls.append(payload)
        if len(calls) == 1:
            return httpx.Response(
                200,
                json={
                    "results": [
                        {"vulns": [{"id": "DEBIAN-CVE-fixture"}], "next_page_token": "page2"},
                        {},
                    ]
                },
            )
        return httpx.Response(
            200,
            json={
                "results": [{"vulns": [{"id": "DEBIAN-CVE-fixture"}, {"id": "DEBIAN-CVE-other"}]}]
            },
        )

    packages = [
        {"ecosystem": "Debian:13", "name": name, "version": "1:2.0-3"}
        for name in ["first", "second"]
    ]
    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        findings = audit.query(client, packages)
    assert len(findings) == 2 and {row["name"] for row in findings} == {"first"}
    assert calls[1]["queries"] == [
        {
            "package": {"ecosystem": "Debian:13", "name": "first"},
            "version": "1:2.0-3",
            "page_token": "page2",
        }
    ]


@pytest.mark.parametrize(
    "response",
    [
        {"results": []},
        {"results": [{"error": "failed"}]},
        {"results": [{"vulns": [{"id": "invalid/id"}]}]},
        {"results": [{"next_page_token": 1}]},
    ],
)
def test_incomplete_or_invalid_osv_results_never_pass(response):
    with httpx.Client(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=response))
    ) as client:
        with pytest.raises(ValueError):
            audit.query(client, [{"ecosystem": "Debian:13", "name": "fixture", "version": "1"}])
