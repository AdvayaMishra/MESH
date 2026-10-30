"""Create explicitly synthetic development data bound to an existing Auth identity."""

import argparse
from uuid import UUID

from app.auth import Principal
from app.core.config import settings
from app.core.db import SessionFactory, assert_runtime_role, tenant_context
from app.models import Membership, Organization, identifier
from app.services import emit
from app.vader import simulate

parser = argparse.ArgumentParser()
parser.add_argument("--owner-id", required=True, type=UUID)
parser.add_argument("--owner-email", required=True)
args = parser.parse_args()
if settings().environment != "development":
    raise RuntimeError("Seed data is restricted to development")
organization_id = identifier()
with SessionFactory.begin() as db:
    assert_runtime_role(db)
    tenant_context(db, organization_id, str(args.owner_id))
    db.add(Organization(id=organization_id, name="Synthetic MESH demonstration"))
    db.flush()
    db.add(
        Membership(
            organization_id=organization_id,
            user_id=str(args.owner_id),
            email=args.owner_email.lower(),
            role="owner",
        )
    )
    db.flush()
    principal = Principal(str(args.owner_id), organization_id, "owner")
    emit(db, principal, "organization.created", organization_id)
    simulate(db, principal, "seed")
print("Synthetic organization ID:", organization_id)
