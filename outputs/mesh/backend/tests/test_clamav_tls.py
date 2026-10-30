import ipaddress
import socket
import ssl
import struct
import threading
from datetime import UTC, datetime, timedelta

import pytest
from app.core.config import Settings, settings
from app.documents import malware_gate
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from fastapi import HTTPException
from pydantic import ValidationError


@pytest.fixture
def scanner(tmp_path, monkeypatch):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Synthetic ClamAV TLS fixture")])
    now = datetime.now(UTC)
    certificate = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=1))
        .not_valid_after(now + timedelta(days=1))
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .add_extension(
            x509.SubjectAlternativeName(
                [
                    x509.IPAddress(ipaddress.ip_address("127.0.0.1")),
                    x509.DNSName("clamav.fixture.invalid"),
                ]
            ),
            critical=False,
        )
        .sign(key, hashes.SHA256())
    )
    cert = tmp_path / "fixture-ca.pem"
    private = tmp_path / "fixture-key.pem"
    cert.write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
    private.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(cert, private)
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    listener.settimeout(3)
    state = {"content": b"", "reply": b"stream: OK\0", "tls": False}

    def serve():
        try:
            raw, _ = listener.accept()
            with raw, context.wrap_socket(raw, server_side=True) as connection:
                connection.settimeout(3)
                state["tls"] = True

                def exact(size):
                    value = bytearray()
                    while len(value) < size:
                        part = connection.recv(size - len(value))
                        if not part:
                            raise OSError("Fixture connection ended")
                        value.extend(part)
                    return bytes(value)

                if exact(10) != b"zINSTREAM\0":
                    raise OSError("Unexpected fixture command")
                while True:
                    size = struct.unpack("!I", exact(4))[0]
                    if not size:
                        break
                    if size > 65536:
                        raise OSError("Fixture chunk exceeded bounds")
                    state["content"] += exact(size)
                connection.sendall(state["reply"])
        except OSError:
            pass

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    config = settings()
    monkeypatch.setattr(config, "clamav_host", "127.0.0.1")
    monkeypatch.setattr(config, "clamav_port", listener.getsockname()[1])
    monkeypatch.setattr(config, "clamav_tls", True)
    monkeypatch.setattr(config, "clamav_ca_file", str(cert))
    try:
        yield state
    finally:
        listener.close()
        thread.join(timeout=4)


def test_actual_tls_screening_transmits_complete_framed_content(scanner, monkeypatch):
    monkeypatch.setattr(settings(), "clamav_tls_server_name", "clamav.fixture.invalid")
    content = b"wholly-fictional-image-fixture" * 5000
    malware_gate(content)
    assert scanner["tls"] is True
    assert scanner["content"] == content


@pytest.mark.parametrize(
    "reply,status",
    [
        (b"stream: PRIVATE_FIXTURE_SIGNATURE FOUND\0", 422),
        (b"stream: ERROR\0", 503),
        (b"stream: OK", 503),
    ],
)
def test_actual_tls_verdicts_fail_closed_without_native_signature_details(scanner, reply, status):
    scanner["reply"] = reply
    with pytest.raises(HTTPException) as error:
        malware_gate(b"fictional fixture")
    assert error.value.status_code == status
    assert "PRIVATE_FIXTURE_SIGNATURE" not in error.value.detail


@pytest.mark.parametrize("failure", ["untrusted_ca", "wrong_hostname"])
def test_tls_verification_failure_prevents_any_document_payload(scanner, monkeypatch, failure):
    if failure == "untrusted_ca":
        monkeypatch.setattr(settings(), "clamav_ca_file", "")
    else:
        monkeypatch.setattr(settings(), "clamav_tls_server_name", "wrong.fixture.invalid")
    with pytest.raises(HTTPException) as error:
        malware_gate(b"private-document-must-not-be-transmitted")
    assert error.value.status_code == 503
    assert scanner["content"] == b""


def test_exhausted_total_scan_budget_prevents_connection(monkeypatch):
    monkeypatch.setattr(settings(), "clamav_host", "127.0.0.1")
    monkeypatch.setattr(settings(), "clamav_tls", False)
    ticks = iter([0, 21])
    monkeypatch.setattr("app.documents.monotonic", lambda: next(ticks))
    monkeypatch.setattr(
        "app.documents.socket.create_connection",
        lambda *args, **kwargs: pytest.fail("Expired budget contacted scanner"),
    )
    with pytest.raises(HTTPException) as error:
        malware_gate(b"fixture")
    assert error.value.status_code == 503


def production(**overrides):
    return Settings(
        _env_file=None,
        environment="production",
        test_mode=False,
        supabase_url="https://identity.example.com",
        require_privileged_mfa=True,
        auth_rate_secret="a" * 48,
        redis_url="rediss://default:fixture@redis.example.com:6380/0",
        database_url="postgresql+psycopg://runtime:fixture@database.example.com/mesh?sslmode=verify-full&sslrootcert=system",
        **overrides,
    )


def test_production_rejects_remote_plaintext_screening():
    with pytest.raises(ValidationError, match="remote malware screening requires verified TLS"):
        production(clamav_host="remote-scanner.example.com")


@pytest.mark.parametrize("host", ["127.0.0.1", "::1", "localhost"])
def test_production_accepts_explicit_loopback_sidecar_endpoint(host):
    assert production(clamav_host=host).clamav_tls is False


def test_production_accepts_verified_tls_remote_endpoint():
    assert production(clamav_host="remote-scanner.example.com", clamav_tls=True).clamav_tls


@pytest.mark.parametrize("port", [0, -1, 65536])
def test_scanner_port_is_bounded(port):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, clamav_port=port)


@pytest.mark.parametrize(
    "name", ["https://scanner.example", "scanner@other.example", "scanner\r\n", "*"]
)
def test_scanner_tls_server_name_cannot_be_a_url_or_injected_value(name):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, clamav_tls_server_name=name)


def test_scanner_ca_path_requires_an_explicit_absolute_location():
    with pytest.raises(ValidationError, match="absolute operator-configured"):
        Settings(_env_file=None, clamav_ca_file="relative/private-ca.pem")
