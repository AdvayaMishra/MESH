import os

os.environ["TEST_MODE"] = "true"
os.environ["DATABASE_URL"] = "sqlite://"

import pytest
from app.auth import Identity, identity
from app.core.db import Base, session
from app.main import app
from app.models import Membership, Organization
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

ORG_A = "11111111-1111-4111-8111-111111111111"
ORG_B = "22222222-2222-4222-8222-222222222222"
OWNER = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
HR = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
DEV = "cccccccc-cccc-4ccc-8ccc-cccccccccccc"
ANALYST = "dddddddd-dddd-4ddd-8ddd-dddddddddddd"
ANALYST2 = "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee"


@pytest.fixture
def db():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )

    @event.listens_for(engine, "connect")
    def foreign_keys(connection, _):
        connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as database:
        database.add_all([Organization(id=ORG_A, name="A"), Organization(id=ORG_B, name="B")])
        database.flush()
        for org in (ORG_A, ORG_B):
            for uid, role in [
                (OWNER, "owner"),
                (HR, "hr"),
                (DEV, "junior_developer"),
                (ANALYST, "security_analyst"),
                (ANALYST2, "security_analyst"),
            ]:
                database.add(
                    Membership(
                        organization_id=org, user_id=uid, email=f"{uid}@example.org", role=role
                    )
                )
        database.commit()
        yield database
    engine.dispose()


@pytest.fixture
def client(db):
    def transaction():
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise

    app.dependency_overrides[session] = transaction
    app.dependency_overrides[identity] = lambda: Identity(OWNER, f"{OWNER}@example.org")
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def login(user_id: str):
    app.dependency_overrides[identity] = lambda: Identity(user_id, f"{user_id}@example.org")


def headers(org=ORG_A):
    return {"X-Organization-ID": org}
