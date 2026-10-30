"""Real loopback TLS transport, explicitly synthetic directory; no real SCIM account."""

import ipaddress
import json
import ssl
import threading
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

import httpx
import pytest
from app.core.config import SCIMBinding, settings
from app.lifecycle_integrations import SCIMClient
from app.scim_provisioning import ProvisioningSCIMClient
from conftest import ORG_A
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from fastapi import HTTPException


@pytest.fixture
def directory(tmp_path, monkeypatch):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name(
        [x509.NameAttribute(NameOID.COMMON_NAME, "MESH synthetic loopback SCIM fixture")]
    )
    current = datetime.now(UTC)
    certificate = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(current - timedelta(minutes=5))
        .not_valid_after(current + timedelta(days=1))
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .add_extension(
            x509.SubjectAlternativeName([x509.IPAddress(ipaddress.ip_address("127.0.0.1"))]),
            critical=False,
        )
        .sign(key, hashes.SHA256())
    )
    cert = tmp_path / "fixture-cert.pem"
    private = tmp_path / "fixture-key.pem"
    cert.write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
    private.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    state = {
        "active": True,
        "version": 1,
        "calls": [],
        "race": False,
        "created": True,
        "subject": None,
        "lose_create_response": False,
    }

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def response(self, status, data=None, etag=None):
            body = json.dumps(data).encode() if data is not None else b""
            self.send_response(status)
            self.send_header("Content-Type", "application/scim+json")
            self.send_header("Content-Length", str(len(body)))
            if etag:
                self.send_header("ETag", etag)
            self.end_headers()
            self.wfile.write(body)

        def allowed(self):
            return (
                urlsplit(self.path).path in {"/v2/Users/fixture", "/v2/Users"}
                and self.headers.get("Authorization") == "Bearer synthetic-wire-token"
            )

        def do_GET(self):
            if not self.allowed():
                return self.response(403)
            state["calls"].append("GET")
            if urlsplit(self.path).path == "/v2/Users":
                return self.response(
                    200,
                    {
                        "totalResults": int(state["created"]),
                        "Resources": [{"id": "fixture"}] if state["created"] else [],
                    },
                )
            if not state["created"]:
                return self.response(404)
            version = 'W/"' + str(state["version"]) + '"'
            self.response(
                200,
                {
                    "id": "fixture",
                    "userName": "fixture@example.invalid",
                    "active": state["active"],
                    "externalId": state["subject"],
                },
                version,
            )
            if state["race"]:
                state["version"] += 1

        def do_POST(self):
            if not self.allowed() or urlsplit(self.path).path != "/v2/Users":
                return self.response(403)
            state["calls"].append("POST")
            if state["created"]:
                return self.response(409)
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 2048:
                return self.response(413)
            payload = json.loads(self.rfile.read(length))
            if (
                payload.get("active") is not False
                or payload.get("userName") != "fixture@example.invalid"
            ):
                return self.response(400)
            state.update(created=True, active=False, version=1, subject=payload["externalId"])
            if state["lose_create_response"]:
                self.close_connection = True
                return
            self.response(201, {"id": "fixture"})

        def do_PATCH(self):
            if not self.allowed():
                return self.response(403)
            state["calls"].append("PATCH")
            if self.headers.get("If-Match") != 'W/"' + str(state["version"]) + '"':
                return self.response(412)
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 2048:
                return self.response(413)
            payload = json.loads(self.rfile.read(length))
            operations = payload.get("Operations", [])
            if (
                len(operations) != 1
                or operations[0].get("op") != "replace"
                or operations[0].get("path") != "active"
                or type(operations[0].get("value")) is not bool
            ):
                return self.response(400)
            state["active"] = operations[0]["value"]
            state["version"] += 1
            self.response(204)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(cert, private)
    server.socket = context.wrap_socket(server.socket, server_side=True)
    thread = threading.Thread(
        target=server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True
    )
    thread.start()
    monkeypatch.setattr(
        settings(),
        "scim_bindings",
        {
            ORG_A: SCIMBinding(
                base_url=f"https://127.0.0.1:{server.server_port}/v2", token="synthetic-wire-token"
            )
        },
    )
    client_context = ssl.create_default_context(cafile=str(cert))
    try:
        yield state, client_context
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_actual_tls_scim_revocation_sends_conditional_request_and_rechecks(directory):
    state, context = directory
    with httpx.Client(verify=context, trust_env=False) as client:
        SCIMClient(ORG_A, client).revoke("fixture", "fixture@example.invalid")
    assert state["active"] is False and state["calls"] == ["GET", "PATCH", "GET"]


def test_actual_tls_scim_race_is_rejected_without_changing_account(directory):
    state, context = directory
    state["race"] = True
    with httpx.Client(verify=context, trust_env=False) as client:
        with pytest.raises(HTTPException) as error:
            SCIMClient(ORG_A, client).revoke("fixture", "fixture@example.invalid")
    assert error.value.status_code == 409
    assert state["active"] is True and state["calls"] == ["GET", "PATCH"]


def test_actual_tls_scim_does_not_accept_untrusted_certificate(directory):
    state, _ = directory
    with httpx.Client(verify=True, trust_env=False) as client:
        with pytest.raises(HTTPException) as error:
            SCIMClient(ORG_A, client).revoke("fixture", "fixture@example.invalid")
    assert error.value.status_code == 503 and state["calls"] == [] and state["active"] is True


def test_actual_tls_inactive_creation_activation_offboarding_and_restoration(
    directory, monkeypatch
):
    state, context = directory
    state["created"] = False
    binding = settings().scim_bindings[ORG_A]
    monkeypatch.setattr(binding, "allow_provisioning", True)
    monkeypatch.setattr(binding, "allow_activation", True)
    subject = "mesh:" + ORG_A + ":aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
    with httpx.Client(verify=context, trust_env=False) as client:
        provisioning = ProvisioningSCIMClient(ORG_A, client)
        assert provisioning.find(subject, "fixture@example.invalid") is None
        assert provisioning.create_inactive(subject, "fixture@example.invalid") == {
            "id": "fixture",
            "active": False,
        }
        assert provisioning.find(subject, "fixture@example.invalid") == {
            "id": "fixture",
            "active": False,
        }
        account = SCIMClient(ORG_A, client)
        account.restore("fixture", "fixture@example.invalid")
        assert state["active"] is True
        account.revoke("fixture", "fixture@example.invalid")
        assert state["active"] is False
        account.restore("fixture", "fixture@example.invalid")
        assert state["active"] is True
    assert state["calls"].count("POST") == 1
    assert state["calls"].count("PATCH") == 3
    assert state["version"] == 4


def test_actual_tls_lost_creation_response_reconciles_by_identity_without_duplicate_post(
    directory, monkeypatch
):
    state, context = directory
    state.update(created=False, lose_create_response=True)
    monkeypatch.setattr(settings().scim_bindings[ORG_A], "allow_provisioning", True)
    subject = "mesh:" + ORG_A + ":aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
    with httpx.Client(verify=context, trust_env=False) as client:
        provisioning = ProvisioningSCIMClient(ORG_A, client)
        with pytest.raises(HTTPException) as error:
            provisioning.create_inactive(subject, "fixture@example.invalid")
        assert error.value.status_code == 503
        assert provisioning.find(subject, "fixture@example.invalid") == {
            "id": "fixture",
            "active": False,
        }
    assert state["calls"].count("POST") == 1


def test_actual_tls_activation_conflict_never_falls_back_to_unconditional_patch(
    directory, monkeypatch
):
    state, context = directory
    state.update(active=False, race=True)
    monkeypatch.setattr(settings().scim_bindings[ORG_A], "allow_activation", True)
    with httpx.Client(verify=context, trust_env=False) as client:
        with pytest.raises(HTTPException) as error:
            SCIMClient(ORG_A, client).restore("fixture", "fixture@example.invalid")
    assert error.value.status_code == 409
    assert state["active"] is False and state["calls"] == ["GET", "PATCH"]


def test_actual_tls_activation_without_explicit_binding_permission_makes_no_request(directory):
    state, context = directory
    state["active"] = False
    with httpx.Client(verify=context, trust_env=False) as client:
        with pytest.raises(HTTPException) as error:
            SCIMClient(ORG_A, client).restore("fixture", "fixture@example.invalid")
    assert error.value.status_code == 503 and state["calls"] == []
