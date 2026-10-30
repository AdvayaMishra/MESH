import gzip
from types import SimpleNamespace

import httpx
import pytest
from app import aws_billing, documents
from app.aws_billing import AWSBillingAdapter
from app.core.config import settings
from app.documents import PrivateStorage
from conftest import ORG_A
from fastapi import HTTPException
from pydantic import SecretStr
from test_aws_billing import CE, IDENTITY, TODAY, response


@pytest.fixture
def storage_settings(monkeypatch):
    monkeypatch.setattr(settings(), "supabase_url", "https://storage.example.invalid")
    monkeypatch.setattr(settings(), "supabase_storage_key", SecretStr("sb_secret_synthetic"))


@pytest.mark.parametrize(
    "headers",
    [
        {"Content-Length": "-1"},
        {"Content-Length": "bad"},
        {"Content-Length": "2097153"},
        {"Content-Length": "999999999999999999999"},
        {"Content-Length": "4,4"},
        {"Content-Length": "3"},
        {"Content-Encoding": "gzip"},
        {"Content-Encoding": "br"},
    ],
)
def test_storage_rejects_ambiguous_oversized_or_encoded_responses(storage_settings, headers):
    def handler(request):
        assert request.headers["accept-encoding"] == "identity"
        content = gzip.compress(b"{}") if headers.get("Content-Encoding") == "gzip" else b"{}"
        # br bytes are deliberately not decoded by a custom stream until after metadata validation.
        return httpx.Response(200, headers=headers, stream=httpx.ByteStream(content))

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(HTTPException) as error:
            PrivateStorage(client).request("POST", "object/list/mesh-identity", json={})
    assert error.value.status_code == 503


@pytest.mark.parametrize("method,status", [("DELETE", 202), ("GET", 206), ("POST", 202)])
def test_async_or_partial_storage_responses_are_not_confirmed_success(
    storage_settings, method, status
):
    with httpx.Client(
        transport=httpx.MockTransport(lambda _: httpx.Response(status, json={}))
    ) as client:
        with pytest.raises(HTTPException) as error:
            PrivateStorage(client).request(method, "object/mesh-identity")
    assert error.value.status_code == 503


def test_trickling_storage_response_hits_elapsed_budget_and_closes(storage_settings, monkeypatch):
    clock = [0]
    monkeypatch.setattr(documents, "monotonic", lambda: clock[0])

    class Trickle(httpx.SyncByteStream):
        closed = False
        chunks = 0

        def __iter__(self):
            for value in [b"{", b'"x":', b"1", b"}"]:
                self.chunks += 1
                clock[0] += 7
                yield value

        def close(self):
            self.closed = True

    stream = Trickle()
    with httpx.Client(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, stream=stream))
    ) as client:
        with pytest.raises(HTTPException) as error:
            PrivateStorage(client).request("POST", "object/list/mesh-identity")
    assert error.value.status_code == 503 and stream.closed and stream.chunks == 3


def test_late_storage_headers_are_not_accepted(storage_settings, monkeypatch):
    clock = [0]
    monkeypatch.setattr(documents, "monotonic", lambda: clock[0])

    def handler(_):
        clock[0] = 21
        return httpx.Response(200, json={})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(HTTPException):
            PrivateStorage(client).request("POST", "object/list/mesh-identity")


@pytest.mark.parametrize("stage", ["provider", "group_processing", "publication"])
def test_billing_rejects_late_final_response_or_processing_without_returning_total(
    monkeypatch, stage
):
    monkeypatch.setattr(aws_billing, "now", lambda: TODAY)
    clock = [0]
    monkeypatch.setattr(aws_billing, "time", SimpleNamespace(monotonic=lambda: clock[0]))

    class Slow(CE):
        def get_cost_and_usage(self, **kwargs):
            value = super().get_cost_and_usage(**kwargs)
            if stage == "provider":
                clock[0] = 61
            return value

    if stage == "group_processing":
        original = aws_billing.ServiceCost

        def delayed(**kwargs):
            value = original(**kwargs)
            clock[0] = 61
            return value

        monkeypatch.setattr(aws_billing, "ServiceCost", delayed)
    elif stage == "publication":
        original = aws_billing.AWSBillingReport.model_dump_json

        def delayed(self, *args, **kwargs):
            value = original(self, *args, **kwargs)
            clock[0] = 61
            return value

        monkeypatch.setattr(aws_billing.AWSBillingReport, "model_dump_json", delayed)
    client = Slow([response()])
    with pytest.raises(HTTPException) as error:
        AWSBillingAdapter(ORG_A, IDENTITY, client).collect("2026-09")
    assert error.value.status_code == 503 and len(client.calls) == 1


def test_case_variant_encoding_header_cannot_override_identity(storage_settings):
    def handler(request):
        assert request.headers.get_list("accept-encoding") == ["identity"]
        return httpx.Response(200, json={})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        assert (
            PrivateStorage(client).request(
                "POST",
                "object/list/mesh-identity",
                headers={"accept-encoding": "gzip", "ACCEPT-ENCODING": "br"},
            )
            == {}
        )


def test_expired_client_setup_budget_never_dispatches_mutation(storage_settings, monkeypatch):
    clock = [0]
    monkeypatch.setattr(documents, "monotonic", lambda: clock[0])
    client = httpx.Client(
        transport=httpx.MockTransport(lambda _: pytest.fail("Expired budget dispatched mutation"))
    )

    def slow_setup(**kwargs):
        clock[0] = 21
        return client

    monkeypatch.setattr(documents.httpx, "Client", slow_setup)
    with pytest.raises(HTTPException) as error:
        PrivateStorage().request("DELETE", "object/mesh-identity")
    assert error.value.status_code == 503 and client.is_closed
