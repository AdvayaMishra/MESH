import pytest
from app.auth import Principal
from app.domains import create_challenge, verify_challenge
from app.models import Organization
from conftest import ORG_A, ORG_B, OWNER
from fastapi import HTTPException


def test_both_domain_proofs_required(db, monkeypatch):
    p = Principal(OWNER, ORG_A, "owner")
    record, token = create_challenge(db, p, "https://example.com")
    db.flush()
    monkeypatch.setattr("app.domains.website_proof", lambda _: token)
    monkeypatch.setattr("app.domains.dns_proofs", lambda _: ["wrong"])
    assert verify_challenge(db, p, record.id)["status"] == "pending"
    assert db.get(Organization, ORG_A).verification_status == "unverified"
    monkeypatch.setattr("app.domains.dns_proofs", lambda _: [token])
    assert verify_challenge(db, p, record.id)["status"] == "verified"
    with pytest.raises(HTTPException):
        verify_challenge(db, p, record.id)


def test_domain_retry_limit_and_cross_tenant(db, monkeypatch):
    p = Principal(OWNER, ORG_A, "owner")
    record, token = create_challenge(db, p, "https://example.com")
    db.flush()
    monkeypatch.setattr("app.domains.website_proof", lambda _: "wrong")
    monkeypatch.setattr("app.domains.dns_proofs", lambda _: [])
    for _ in range(5):
        verify_challenge(db, p, record.id)
    with pytest.raises(HTTPException) as exc:
        verify_challenge(db, p, record.id)
    assert exc.value.status_code == 409
    with pytest.raises(HTTPException) as exc:
        verify_challenge(db, Principal(OWNER, ORG_B, "owner"), record.id)
    assert exc.value.status_code == 404


@pytest.mark.parametrize("address", ["127.0.0.1", "169.254.169.254", "10.0.0.4"])
def test_website_fetch_blocks_private_dns_before_connection(monkeypatch, address):
    from app.domains import website_proof

    monkeypatch.setattr(
        "app.domains.socket.getaddrinfo", lambda *a, **k: [(2, 1, 6, "", (address, 443))]
    )
    monkeypatch.setattr(
        "app.domains.PinnedHTTPS", lambda *a: pytest.fail("Unsafe socket attempted")
    )
    with pytest.raises(ValueError):
        website_proof("example.org")


@pytest.mark.parametrize(
    "status,body,valid",
    [(200, b"mesh-proof", True), (302, b"redirect", False), (200, b"x" * 4097, False)],
)
def test_website_redirect_size_and_cleanup(monkeypatch, status, body, valid):
    from app.domains import website_proof

    closed = []

    class Connection:
        def __init__(self, host, address):
            assert host == "example.org" and address == "8.8.8.8"

        def request(self, method, path, headers):
            assert method == "GET" and path == "/.well-known/mesh-verification.txt"

        def getresponse(self):
            return self

        def getheader(self, name, default):
            return default

        def read(self, size):
            return body[:size]

        def close(self):
            closed.append(True)

    Connection.status = status
    monkeypatch.setattr(
        "app.domains.socket.getaddrinfo", lambda *a, **k: [(2, 1, 6, "", ("8.8.8.8", 443))]
    )
    monkeypatch.setattr("app.domains.PinnedHTTPS", Connection)
    if valid:
        assert website_proof("example.org") == "mesh-proof"
    else:
        with pytest.raises(ValueError):
            website_proof("example.org")
    assert closed == [True]
