import hashlib
import http.client
import secrets
import socket
import ssl
from contextlib import closing
from datetime import timedelta

import dns.exception
import dns.resolver
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import Principal
from app.core.time import as_utc
from app.models import DomainChallenge, Organization, identifier, now
from app.security import normalize_domain, validate_addresses
from app.services import emit


class PinnedHTTPS(http.client.HTTPSConnection):
    def __init__(self, host: str, address: str):
        self.tls_context = ssl.create_default_context()
        super().__init__(host, timeout=5, context=self.tls_context)
        self.address = address

    def connect(self):
        # Resolve once, validate every answer, then connect to the validated IP.
        # TLS still authenticates the original DNS name; Host also remains the DNS name.
        connection = socket.create_connection((self.address, 443), timeout=5)
        try:
            self.sock = self.tls_context.wrap_socket(connection, server_hostname=self.host)
        except Exception:
            connection.close()
            raise


def website_proof(domain: str) -> str:
    answers = socket.getaddrinfo(domain, 443, type=socket.SOCK_STREAM)
    addresses = sorted({str(entry[4][0]) for entry in answers})
    validate_addresses(addresses)
    with closing(PinnedHTTPS(domain, addresses[0])) as connection:
        connection.request(
            "GET",
            "/.well-known/mesh-verification.txt",
            headers={"Accept": "text/plain", "User-Agent": "MESH-Domain-Verification/1"},
        )
        response = connection.getresponse()
        # Never follow redirects; never accept compressed or oversized content.
        if (
            response.status != 200
            or response.getheader("Content-Encoding", "identity") != "identity"
        ):
            raise ValueError("Verification file unavailable")
        body = response.read(4097)
        if len(body) > 4096:
            raise ValueError("Verification file exceeds limit")
        return body.decode("ascii").strip()


def dns_proofs(domain: str) -> list[str]:
    answers = dns.resolver.resolve("_mesh-verification." + domain, "TXT", lifetime=5)
    return [b"".join(record.strings).decode("ascii").strip() for record in answers]


def create_challenge(db: Session, p: Principal, website: str) -> tuple[DomainChallenge, str]:
    domain = normalize_domain(website)
    org = db.scalar(
        select(Organization)
        .where(Organization.id == p.organization_id)
        .with_for_update(key_share=True)
    )
    if org is None:
        raise HTTPException(404, "Organization not found")
    pending = db.scalar(
        select(DomainChallenge).where(
            DomainChallenge.organization_id == p.organization_id,
            DomainChallenge.status == "pending",
            DomainChallenge.expires_at > now(),
        )
    )
    if org.verification_status == "verified" or pending:
        raise HTTPException(409, "Organization is verified or has an unexpired challenge")
    org.domain = domain
    token = "mesh-verification=" + secrets.token_urlsafe(32)
    record = DomainChallenge(
        id=identifier(),
        organization_id=p.organization_id,
        domain=domain,
        token_hash=hashlib.sha256(token.encode()).hexdigest(),
        expires_at=now() + timedelta(minutes=30),
    )
    db.add(record)
    emit(db, p, "organization.verification.started", record.id)
    return record, token


def verify_challenge(db: Session, p: Principal, challenge_id: str) -> dict:
    from app.services import lock_tenant

    lock_tenant(db, p.organization_id)
    record = db.scalar(
        select(DomainChallenge)
        .where(
            DomainChallenge.organization_id == p.organization_id, DomainChallenge.id == challenge_id
        )
        .with_for_update()
    )
    if not record:
        raise HTTPException(404, "Challenge not found")
    if record.status != "pending" or record.attempts >= 5 or as_utc(record.expires_at) <= now():
        raise HTTPException(409, "Challenge expired, consumed or exhausted")
    record.attempts += 1
    website_ok = dns_ok = False
    try:
        website_ok = secrets.compare_digest(
            hashlib.sha256(website_proof(record.domain).encode()).hexdigest(), record.token_hash
        )
        dns_ok = any(
            secrets.compare_digest(hashlib.sha256(value.encode()).hexdigest(), record.token_hash)
            for value in dns_proofs(record.domain)
        )
    except (OSError, ValueError, http.client.HTTPException, dns.exception.DNSException):
        dns_ok = False
    if website_ok and dns_ok:
        org = db.get(Organization, p.organization_id)
        if org is None:
            raise HTTPException(404, "Organization not found")
        org.verification_status = "verified"
        record.status = "verified"
        emit(db, p, "organization.verified", record.id)
    else:
        from app.services import audit

        audit(db, p, "organization.verification.failed", record.id)
    return {
        "status": record.status,
        "website_verified": website_ok,
        "dns_verified": dns_ok,
        "attempts_remaining": 5 - record.attempts,
    }
