"""Bind lifecycle approvals to exact tenant accounts and configured authorities."""

import hashlib
import json

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import IntegrationAccount, Membership


def account_review(account: IntegrationAccount, member: Membership) -> dict:
    binding = settings().scim_bindings.get(account.organization_id)
    authority = binding.base_url if account.provider == "scim" and binding else None
    value = {
        "organization_id": account.organization_id,
        "user_id": account.user_id,
        "provider": account.provider,
        "external_id": account.external_id,
        "email": member.email.strip().lower(),
        "authority": authority,
    }
    return {
        "id": account.id,
        "provider": account.provider,
        "review_digest": hashlib.sha256(
            json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest(),
    }


def account_inventory(db: Session, member: Membership) -> list[dict]:
    accounts = db.scalars(
        select(IntegrationAccount)
        .where(
            IntegrationAccount.organization_id == member.organization_id,
            IntegrationAccount.user_id == member.user_id,
        )
        .order_by(IntegrationAccount.id)
    ).all()
    return [account_review(account, member) for account in accounts]


def require_reviewed_inventory(db: Session, member: Membership, steps: list[dict]) -> None:
    expected = sorted(
        ({key: step.get(key) for key in ("id", "provider", "review_digest")} for step in steps),
        key=lambda item: str(item["id"]),
    )
    if expected != account_inventory(db, member):
        raise HTTPException(
            409, "External account inventory changed; fresh lifecycle review required"
        )


def require_reviewed_account(step: dict, account: IntegrationAccount, member: Membership) -> None:
    reviewed = account_review(account, member)
    if any(step.get(key) != value for key, value in reviewed.items()):
        raise HTTPException(409, "External identity or authority changed after lifecycle review")
