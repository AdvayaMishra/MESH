import httpx
import pytest
from app.core.config import SCIMBinding, settings
from app.lifecycle_integrations import SCIMClient
from conftest import ORG_A
from fastapi import HTTPException

EMAIL = "fixture@example.invalid"
TAG = 'W/"version-1"'


def binding(monkeypatch, **kwargs):
    monkeypatch.setattr(
        settings(),
        "scim_bindings",
        {
            ORG_A: SCIMBinding(
                base_url="https://scim.example.invalid/v2",
                token="synthetic-token",
                allow_activation=True,
                **kwargs,
            )
        },
    )


def test_metadata_version_is_used_as_if_match_and_result_is_reverified(monkeypatch):
    binding(monkeypatch)
    active = True
    calls = []

    def handler(request):
        nonlocal active
        calls.append(request.method)
        if request.method == "PATCH":
            assert request.headers["If-Match"] == TAG
            active = False
            return httpx.Response(204)
        return httpx.Response(
            200,
            json={"id": "fixture", "userName": EMAIL, "active": active, "meta": {"version": TAG}},
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        SCIMClient(ORG_A, client).revoke("fixture", EMAIL)
    assert calls == ["GET", "PATCH", "GET"]


def test_missing_version_fails_closed_before_patch(monkeypatch):
    binding(monkeypatch)
    calls = []

    def handler(request):
        calls.append(request.method)
        return httpx.Response(200, json={"id": "fixture", "userName": EMAIL, "active": True})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(HTTPException) as error:
            SCIMClient(ORG_A, client).revoke("fixture", EMAIL)
    assert error.value.status_code == 503 and calls == ["GET"]


@pytest.mark.parametrize(
    "version", ["*", '"one", "two"', 'W/"bad\nvalue"', '"' + ("x" * 129) + '"', 42]
)
def test_invalid_provider_versions_cannot_inject_headers_or_mutate(monkeypatch, version):
    binding(monkeypatch)
    calls = []

    def handler(request):
        calls.append(request.method)
        return httpx.Response(
            200,
            json={"id": "fixture", "userName": EMAIL, "active": True, "meta": {"version": version}},
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(HTTPException) as error:
            SCIMClient(ORG_A, client).revoke("fixture", EMAIL)
    assert error.value.status_code == 503 and calls == ["GET"]


def test_header_and_resource_version_disagreement_is_not_trusted(monkeypatch):
    binding(monkeypatch)
    calls = []

    def handler(request):
        calls.append(request.method)
        return httpx.Response(
            200,
            headers={"ETag": TAG},
            json={
                "id": "fixture",
                "userName": EMAIL,
                "active": True,
                "meta": {"version": '"other"'},
            },
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(HTTPException) as error:
            SCIMClient(ORG_A, client).revoke("fixture", EMAIL)
    assert error.value.status_code == 503 and calls == ["GET"]


@pytest.mark.parametrize("require_version", [True, False])
def test_precondition_failure_never_retries_without_condition(monkeypatch, require_version):
    binding(monkeypatch, require_version=require_version)
    calls = []

    def handler(request):
        calls.append(request.method)
        if request.method == "PATCH":
            assert request.headers["If-Match"] == TAG
            return httpx.Response(412, json={"detail": "DO_NOT_EXPOSE"})
        return httpx.Response(
            200, headers={"ETag": TAG}, json={"id": "fixture", "userName": EMAIL, "active": True}
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(HTTPException) as error:
            SCIMClient(ORG_A, client).revoke("fixture", EMAIL)
    assert error.value.status_code == 409 and calls == ["GET", "PATCH"]
    assert "DO_NOT_EXPOSE" not in error.value.detail


def test_explicit_unversioned_provider_configuration_is_required_for_legacy_updates(monkeypatch):
    binding(monkeypatch, require_version=False)
    active = True

    def handler(request):
        nonlocal active
        if request.method == "PATCH":
            assert "If-Match" not in request.headers
            active = False
            return httpx.Response(204)
        return httpx.Response(200, json={"id": "fixture", "userName": EMAIL, "active": active})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        SCIMClient(ORG_A, client).revoke("fixture", EMAIL)


def test_already_inactive_identity_does_not_require_a_mutation_version(monkeypatch):
    binding(monkeypatch)
    calls = []

    def handler(request):
        calls.append(request.method)
        return httpx.Response(200, json={"id": "fixture", "userName": EMAIL, "active": False})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        SCIMClient(ORG_A, client).revoke("fixture", EMAIL)
    assert calls == ["GET"]


def test_direct_patch_cannot_omit_required_precondition(monkeypatch):
    binding(monkeypatch)
    with httpx.Client(
        transport=httpx.MockTransport(lambda request: pytest.fail("Unconditional PATCH sent"))
    ) as client:
        with pytest.raises(HTTPException) as error:
            SCIMClient(ORG_A, client).request("PATCH", "fixture", {"Operations": []})
    assert error.value.status_code == 503
