import json

import httpx
import pytest
from app.core.config import SCIMBinding, settings
from app.lifecycle_integrations import SCIMClient
from app.scim_provisioning import ProvisioningSCIMClient
from conftest import ORG_A
from fastapi import HTTPException

SUBJECT = "mesh:" + ORG_A + ":33333333-3333-4333-8333-333333333333"
EMAIL = "employee@example.invalid"


@pytest.fixture
def configured(monkeypatch):
    monkeypatch.setattr(
        settings(),
        "scim_bindings",
        {
            ORG_A: SCIMBinding(
                base_url="https://scim.example.org/v2",
                token="fixture-provisioning-token",
                allow_provisioning=True,
                allow_activation=True,
            )
        },
    )


def user(**values):
    return {
        "id": "verified-user",
        "userName": EMAIL,
        "externalId": SUBJECT,
        "active": False,
        **values,
    }


def test_scim_creation_is_inactive_and_verifies_the_returned_resource(configured):
    methods = []

    def handler(request):
        methods.append(request.method)
        assert request.headers["Accept-Encoding"] == "identity"
        if request.method == "POST":
            assert request.url.path == "/v2/Users"
            data = json.loads(request.content)
            assert (
                data["externalId"] == SUBJECT
                and data["userName"] == EMAIL
                and data["active"] is False
            )
            return httpx.Response(201, json={"id": "verified-user"})
        assert request.url.path == "/v2/Users/verified-user"
        return httpx.Response(200, json=user())

    with httpx.Client(transport=httpx.MockTransport(handler)) as transport:
        assert ProvisioningSCIMClient(ORG_A, transport).create_inactive(SUBJECT, EMAIL) == {
            "id": "verified-user",
            "active": False,
        }
    assert methods == ["POST", "GET"]


def test_discovery_is_filtered_and_confirms_identity_with_a_separate_get(configured):
    paths = []

    def handler(request):
        paths.append(request.url.path)
        if request.url.path == "/v2/Users":
            assert request.url.params["filter"] == 'externalId eq "' + SUBJECT + '"'
            assert request.url.params["count"] == "2"
            return httpx.Response(
                200, json={"totalResults": 1, "Resources": [{"id": "verified-user"}]}
            )
        return httpx.Response(200, json=user())

    with httpx.Client(transport=httpx.MockTransport(handler)) as transport:
        assert (
            ProvisioningSCIMClient(ORG_A, transport).find(SUBJECT, EMAIL)["id"] == "verified-user"
        )
    assert paths == ["/v2/Users", "/v2/Users/verified-user"]


@pytest.mark.parametrize(
    "reply",
    [
        {"totalResults": 2, "Resources": [{"id": "a"}, {"id": "b"}]},
        {"totalResults": 1, "Resources": []},
        {"Resources": []},
        {"totalResults": True, "Resources": [{"id": "a"}]},
        {"totalResults": 0},
    ],
)
def test_incomplete_or_ambiguous_discovery_fails_closed(configured, reply):
    with httpx.Client(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json=reply))
    ) as transport:
        with pytest.raises(HTTPException) as error:
            ProvisioningSCIMClient(ORG_A, transport).find(SUBJECT, EMAIL)
    assert error.value.status_code == 409


@pytest.mark.parametrize(
    "reply",
    [
        user(userName="other@example.invalid"),
        user(externalId="different-subject"),
        user(active=True),
        user(active="false"),
        user(id="other-user"),
    ],
)
def test_creation_never_adopts_mismatched_or_active_provider_accounts(configured, reply):
    def handler(request):
        return (
            httpx.Response(201, json={"id": "verified-user"})
            if request.method == "POST"
            else httpx.Response(200, json=reply)
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as transport:
        with pytest.raises(HTTPException):
            ProvisioningSCIMClient(ORG_A, transport).create_inactive(SUBJECT, EMAIL)


def test_disabled_provisioning_makes_no_provider_request(configured, monkeypatch):
    settings().scim_bindings[ORG_A].allow_provisioning = False
    calls = []
    with httpx.Client(
        transport=httpx.MockTransport(lambda request: calls.append(True))
    ) as transport:
        with pytest.raises(HTTPException) as error:
            ProvisioningSCIMClient(ORG_A, transport).find(SUBJECT, EMAIL)
    assert error.value.status_code == 503 and calls == []


@pytest.mark.parametrize(
    "reply",
    [
        httpx.Response(200, content=b"x" * 131073),
        httpx.Response(
            200, stream=httpx.ByteStream(b"not-json"), headers={"content-encoding": "gzip"}
        ),
        httpx.Response(302, headers={"location": "https://other.example.invalid"}),
    ],
)
def test_scim_responses_are_bounded_and_redirects_or_compression_are_rejected(configured, reply):
    calls = []

    def handler(request):
        calls.append(request.url.host)
        return reply

    with httpx.Client(transport=httpx.MockTransport(handler)) as transport:
        with pytest.raises(HTTPException) as error:
            SCIMClient(ORG_A, transport).user("verified-user", EMAIL)
    assert error.value.status_code == 503 and calls == ["scim.example.org"]


def test_scim_overall_time_budget_is_checked_after_headers(configured, monkeypatch):
    ticks = iter([0.0, 21.0])
    monkeypatch.setattr("app.lifecycle_integrations.monotonic", lambda: next(ticks))
    with httpx.Client(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json=user()))
    ) as transport:
        with pytest.raises(HTTPException) as error:
            SCIMClient(ORG_A, transport).user("verified-user", EMAIL)
    assert error.value.status_code == 503
