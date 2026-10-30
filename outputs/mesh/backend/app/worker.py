"""Transactional outbox dispatch with explicit, idempotent integration handlers."""

import argparse
import hashlib
import json
import secrets
from datetime import timedelta

from cryptography.fernet import Fernet
from sqlalchemy import select, true
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.db import SessionFactory, assert_runtime_role, tenant_context
from app.core.time import as_utc
from app.mail import send_invitation
from app.models import Delivery, Invitation, Organization, Outbox, now
from app.services import invitation_issuer


def consume(db: Session, organization_id: str, *, mail_only: bool = False) -> int:
    tenant_context(db, organization_id, "outbox-worker")
    organization = db.get(Organization, organization_id)
    if organization is None:
        raise RuntimeError("Worker tenant must exist")
    messages = db.scalars(
        select(Outbox)
        .where(
            Outbox.organization_id == organization_id,
            Outbox.status == "pending",
            Outbox.topic != "lifecycle.scim.provision",
            Outbox.topic == "mail.invitation" if mail_only else true(),
            Outbox.available_at <= now(),
        )
        .order_by(Outbox.created_at)
        .limit(50)
        .with_for_update(skip_locked=True)
    ).all()
    for message in messages:
        mail_outcome = None
        consumer = (
            "scim-revocation-v1"
            if message.topic == "lifecycle.scim.revoke"
            else "scim-restoration-v1"
            if message.topic == "lifecycle.scim.restore"
            else "local-event-receipt"
        )
        try:
            with db.begin_nested():
                existing = db.scalar(
                    select(Delivery).where(
                        Delivery.organization_id == organization_id,
                        Delivery.message_id == message.id,
                        Delivery.consumer == consumer,
                    )
                )
                if not existing:
                    if message.topic == "mail.invitation":
                        record = db.scalar(
                            select(Invitation).where(
                                Invitation.organization_id == organization_id,
                                Invitation.id == message.payload["invitation_id"],
                            )
                        )
                        if (
                            not record
                            or organization.status != "active"
                            or record.status != "pending"
                        ):
                            mail_outcome = "skipped_inactive"
                        elif as_utc(record.expires_at) <= now():
                            mail_outcome = "skipped_expired"
                        elif (
                            invitation_issuer(db, organization_id, record.creator_id, record.role)
                            is None
                        ):
                            mail_outcome = "skipped_inactive"
                        else:
                            key = settings().mail_encryption_key
                            if key is None:
                                raise RuntimeError("Mail encryption key is unavailable")
                            data = json.loads(
                                Fernet(key.get_secret_value().encode()).decrypt(
                                    message.payload["ciphertext"].encode(), ttl=259200
                                )
                            )
                            if (
                                secrets.compare_digest(
                                    hashlib.sha256(data["token"].encode()).hexdigest(),
                                    record.token_hash,
                                )
                                and data["email"] == record.email
                            ):
                                send_invitation(record.email, data["token"], organization_id)
                                mail_outcome = "smtp_accepted"
                            else:
                                mail_outcome = "skipped_superseded"
                    elif message.topic == "lifecycle.scim.revoke":
                        from app.lifecycle_integrations import revoke_scim

                        revoke_scim(db, organization_id, message.payload)
                    elif message.topic == "lifecycle.scim.restore":
                        from app.lifecycle_integrations import restore_scim

                        restore_scim(db, organization_id, message.payload)
                    db.add(
                        Delivery(
                            organization_id=organization_id,
                            message_id=message.id,
                            consumer=consumer,
                        )
                    )
                    db.flush()
                message.status = "delivered"
                if message.topic == "mail.invitation":
                    message.payload = {
                        "invitation_id": message.payload["invitation_id"],
                        **({"outcome": mail_outcome} if mail_outcome else {}),
                    }
        except Exception:
            message.attempts += 1
            message.status = "dead_letter" if message.attempts >= 5 else "pending"
            message.available_at = now() + timedelta(seconds=min(300, 2**message.attempts))
            if message.topic in {"lifecycle.scim.revoke", "lifecycle.scim.restore"}:
                from app.lifecycle_integrations import record_failure

                record_failure(
                    db, organization_id, message.payload, message.status == "dead_letter"
                )
    return len(messages)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--organization",
        required=True,
        help="Explicit tenant UUID; launch a worker per authorized tenant",
    )
    parser.add_argument("--once", action="store_true")
    parser.add_argument(
        "--mail-only",
        action="store_true",
        help="Deliver invitation mail only; do not run lifecycle integrations",
    )
    args = parser.parse_args()
    from app.provision_worker import run_once as provision_once
    from app.worker_health import run_loop

    def cycle():
        if not args.mail_only:
            provision_once(args.organization)
        with SessionFactory.begin() as db:
            assert_runtime_role(db)
            tenant_context(db, args.organization, "outbox-worker")
            org = db.get(Organization, args.organization)
            if org is None:
                raise RuntimeError("Worker tenant must exist")
            consume(db, args.organization, mail_only=args.mail_only)

    run_loop("outbox", args.organization, cycle, repeat=not args.once, interval=2)


if __name__ == "__main__":
    main()
