"""Opt-in live tests. A missing server is a skip, never claimed as a pass."""

import os
import secrets
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from pathlib import Path
from threading import Barrier

import pytest
from app.auth import Principal
from app.core.db import assert_runtime_role, tenant_context
from app.models import (
    AuditLog,
    AuditSeal,
    Employee,
    IdentityDocument,
    LifecyclePlan,
    Membership,
    Organization,
    Outbox,
    RiskAssessment,
    RiskPolicy,
    SecurityEvent,
    identifier,
    now,
)
from app.services import audit
from psycopg import sql
from sqlalchemy import create_engine, delete, func, select, text, update
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

ADMIN = os.getenv("MESH_POSTGRES_ADMIN_URL", "")
pytestmark = pytest.mark.skipif(
    not ADMIN,
    reason="MESH_POSTGRES_ADMIN_URL is not configured; live PostgreSQL RLS validation pending",
)


@pytest.fixture(scope="module")
def postgres():
    url = make_url(ADMIN)
    if not (url.database or "").startswith("mesh_test_"):
        pytest.fail(
            "Integration database name must start mesh_test_; never point this suite at production"
        )
    root = Path(__file__).resolve().parents[2]
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=root,
        env={**os.environ, "DATABASE_URL": ADMIN},
        check=True,
        capture_output=True,
        timeout=60,
    )
    admin = create_engine(url)
    role = "mesh_test_" + secrets.token_hex(8)
    password = secrets.token_urlsafe(32)
    with admin.begin() as connection:
        with connection.connection.driver_connection.cursor() as cursor:
            cursor.execute(
                sql.SQL("CREATE ROLE {} LOGIN NOSUPERUSER NOBYPASSRLS PASSWORD {}").format(
                    sql.Identifier(role), sql.Literal(password)
                )
            )
            cursor.execute(
                sql.SQL("GRANT USAGE ON SCHEMA public TO {}").format(sql.Identifier(role))
            )
            cursor.execute(
                sql.SQL(
                    "GRANT SELECT,INSERT,UPDATE,DELETE ON ALL TABLES IN SCHEMA public TO {}"
                ).format(sql.Identifier(role))
            )
            cursor.execute(
                sql.SQL(
                    "GRANT EXECUTE ON FUNCTION public.mesh_retire_telemetry(integer,integer) TO {}"
                ).format(sql.Identifier(role))
            )
            cursor.execute(
                sql.SQL(
                    "GRANT EXECUTE ON FUNCTION public.mesh_rehire_clear_project_grants(text) TO {}"
                ).format(sql.Identifier(role))
            )
    org_a, org_b, user = identifier(), identifier(), identifier()
    with Session(admin) as db:
        for org in (org_a, org_b):
            db.add(Organization(id=org, name="RLS fixture"))
        db.flush()
        for org in (org_a, org_b):
            db.add(
                Membership(
                    organization_id=org,
                    user_id=user,
                    email=user + "@example.org",
                    role="junior_developer",
                )
            )
        db.flush()
        for org in (org_a, org_b):
            db.add(
                Employee(
                    organization_id=org, user_id=user, name="Private employee", department="Testing"
                )
            )
            db.add(AuditLog(organization_id=org, actor_id=user, action="fixture", target_id=org))
        db.commit()
    runtime = create_engine(url.set(username=role, password=password))
    yield runtime, org_a, org_b, user
    from app.ai_accounting_pool import close

    close()
    runtime.dispose()
    with admin.begin() as connection:
        with connection.connection.driver_connection.cursor() as cursor:
            cursor.execute(sql.SQL("DROP OWNED BY {}").format(sql.Identifier(role)))
            cursor.execute(sql.SQL("DROP ROLE {}").format(sql.Identifier(role)))
    admin.dispose()


def _held_document_fixture(postgres):
    engine, _, _, _ = postgres
    org, hr, hr2, employee_user = (identifier() for _ in range(4))
    with Session(engine) as db:
        tenant_context(db, org, hr)
        db.add(Organization(id=org, name="Synthetic preservation fixture"))
        db.flush()
        for user, role in ((hr, "hr"), (hr2, "hr"), (employee_user, "junior_developer")):
            db.add(
                Membership(
                    organization_id=org, user_id=user, role=role, email=user + "@example.invalid"
                )
            )
        db.flush()
        employee = Employee(
            organization_id=org, user_id=employee_user, name="Synthetic", department="Test"
        )
        db.add(employee)
        db.flush()
        doc_id = identifier()
        record = IdentityDocument(
            id=doc_id,
            organization_id=org,
            employee_id=employee.id,
            storage_key=f"{org}/{employee.id}/{doc_id}",
            digest="0" * 64,
            media_type="image/png",
            expires_at=now() - timedelta(days=1),
        )
        db.add(record)
        db.flush()
        doc_id = record.id
        db.commit()
    return engine, org, hr, hr2, doc_id


def test_live_document_holds_rls_immutable_history_and_database_preservation(postgres):
    from app.models import DocumentHold

    engine, org, hr, hr2, doc_id = _held_document_fixture(postgres)
    with Session(engine) as db:
        tenant_context(db, org, hr)
        hold = DocumentHold(
            organization_id=org,
            document_id=doc_id,
            request_key=identifier(),
            placed_by=hr,
            reason_code="investigation",
        )
        db.add(hold)
        db.flush()
        hold_id = hold.id
        db.commit()
    forbidden = [
        update(IdentityDocument).where(IdentityDocument.id == doc_id).values(status="deleted"),
        update(IdentityDocument).where(IdentityDocument.id == doc_id).values(storage_key="changed"),
        delete(IdentityDocument).where(IdentityDocument.id == doc_id),
        update(DocumentHold).where(DocumentHold.id == hold_id).values(reason_code="other"),
        delete(DocumentHold).where(DocumentHold.id == hold_id),
        update(DocumentHold)
        .where(DocumentHold.id == hold_id)
        .values(released_at=now(), released_by=hr, release_reason="resolved"),
        update(DocumentHold)
        .where(DocumentHold.id == hold_id)
        .values(released_at=now(), released_by=hr2, release_reason=None),
    ]
    for statement in forbidden:
        with Session(engine) as db:
            tenant_context(db, org, hr)
            with pytest.raises(DBAPIError):
                db.execute(statement)
                db.flush()
    with Session(engine) as db:
        tenant_context(db, identifier(), hr)
        assert db.get(DocumentHold, hold_id) is None
    with Session(engine) as db:
        tenant_context(db, org, hr2)
        db.execute(
            update(DocumentHold)
            .where(DocumentHold.id == hold_id)
            .values(released_at=now(), released_by=hr2, release_reason="resolved")
        )
        db.execute(
            update(IdentityDocument).where(IdentityDocument.id == doc_id).values(status="deleted")
        )
        db.commit()
    with Session(engine) as db:
        tenant_context(db, org, hr2)
        with pytest.raises(DBAPIError):
            db.execute(
                update(DocumentHold)
                .where(DocumentHold.id == hold_id)
                .values(release_reason="other")
            )


def test_live_document_hold_commits_before_waiting_retention_can_delete(postgres, monkeypatch):
    from threading import Event

    from app.document_holds import HoldInput, place
    from app.documents import expire

    engine, org, hr, _, doc_id = _held_document_fixture(postgres)
    locked, waiting, allow_commit = Event(), Event(), Event()
    deleted = []
    monkeypatch.setattr("app.documents.PrivateStorage.delete", lambda _, key: deleted.append(key))

    def preserve():
        with Session(engine) as db:
            tenant_context(db, org, hr)
            place(
                db,
                Principal(hr, org, "hr"),
                doc_id,
                HoldInput(request_key=identifier(), reason_code="dispute"),
            )
            locked.set()
            assert allow_commit.wait(10)
            db.commit()

    def retention():
        assert locked.wait(10)
        with Session(engine) as db:
            tenant_context(db, org, hr)
            waiting.set()
            count = expire(db, Principal("retention-worker", org, "system"))
            db.commit()
            return count

    with ThreadPoolExecutor(max_workers=2) as pool:
        a, b = pool.submit(preserve), pool.submit(retention)
        assert waiting.wait(10)
        allow_commit.set()
        a.result(timeout=15)
        assert b.result(timeout=15) == 0
    assert deleted == []


def test_live_document_authority_refreshes_cached_org_after_waiting_for_suspension(
    postgres, monkeypatch
):
    from threading import Event

    from app.document_authority import authority
    from app.services import lock_tenant

    engine, org, hr, _, _ = _held_document_fixture(postgres)
    cached, locked, waiting = Event(), Event(), Event()
    original = lock_tenant

    def observe_wait(db, organization_id):
        waiting.set()
        return original(db, organization_id)

    monkeypatch.setattr("app.document_authority.lock_tenant", observe_wait)

    def suspend():
        assert cached.wait(10)
        with Session(engine) as db:
            tenant_context(db, org, hr)
            row = lock_tenant(db, org)
            locked.set()
            assert waiting.wait(10)
            row.status = "suspended"
            db.commit()

    def access():
        with Session(engine) as db:
            tenant_context(db, org, hr)
            row = db.get(Organization, org)
            assert row.status == "active"
            cached.set()
            assert locked.wait(10)
            with pytest.raises(HTTPException) as error:
                authority(db, Principal(hr, org, "hr"))
            assert error.value.status_code == 403 and row.status == "suspended"

    from fastapi import HTTPException

    with ThreadPoolExecutor(max_workers=2) as pool:
        a, b = pool.submit(suspend), pool.submit(access)
        a.result(timeout=20)
        b.result(timeout=20)


def test_live_r4_optional_aws_sample_never_enters_finance_or_billing_records(postgres, monkeypatch):
    from app.cloud_integration_api import billing_sample, billing_status
    from app.core.config import settings
    from app.models import BillingCollection, CostRecord
    from fastapi import HTTPException

    engine, org, user = _billing_fixture(postgres)
    monkeypatch.setattr(settings(), "environment", "development")
    monkeypatch.setattr(settings(), "aws_billing_role_bindings", {})
    actor = Principal(user, org, "owner")
    with Session(engine) as db:
        tenant_context(db, org, user)
        assert billing_status(db, actor).state == "not_configured"
        sample = billing_sample(db, actor, period="2026-10")
        assert str(sample.organization_id) == org and sample.synthetic
        assert sample.batch.provenance == "fixture" and not sample.affects_recorded_totals
        assert db.scalar(select(func.count()).select_from(BillingCollection)) == 0
        assert db.scalar(select(func.count()).select_from(CostRecord)) == 0
        assert db.scalar(
            select(AuditLog.id).where(AuditLog.action == "finance.billing.sample_read")
        )
        db.commit()
        with Session(engine) as other:
            tenant_context(other, org, user)
            other.get(Membership, (org, user)).active = False
            other.commit()
        with pytest.raises(HTTPException) as error:
            billing_sample(db, actor, period="2026-10")
        assert error.value.status_code == 403


def test_live_rls_filters_unscoped_and_cross_tenant(postgres):
    engine, org_a, org_b, user = postgres
    with Session(engine) as db:
        assert_runtime_role(db)
        assert db.scalars(select(Employee)).all() == []
        tenant_context(db, org_a, user)
        rows = db.scalars(
            select(Employee)
        ).all()  # Deliberately omit application tenant predicates.
        assert rows and {row.organization_id for row in rows} == {org_a}
        assert db.scalars(select(Employee).where(Employee.organization_id == org_b)).all() == []


def test_live_rls_rejects_cross_tenant_insert(postgres):
    engine, org_a, org_b, user = postgres
    with Session(engine) as db:
        tenant_context(db, org_a, user)
        db.add(
            Employee(organization_id=org_b, user_id=user, name="Forbidden", department="Testing")
        )
        with pytest.raises(DBAPIError):
            db.flush()
        db.rollback()


def test_live_self_membership_discovery_is_read_only_and_excludes_business_tables(postgres):
    engine, org_a, org_b, user = postgres
    with Session(engine) as db:
        assert_runtime_role(db)
        assert db.scalars(select(Membership)).all() == []
        tenant_context(db, "", user)
        # Deliberately omit user/org predicates: the SELECT-only policy must enforce scope.
        rows = db.scalars(select(Membership)).all()
        assert {row.organization_id for row in rows} == {org_a, org_b}
        assert {row.user_id for row in rows} == {user}
        assert db.scalars(select(Employee)).all() == []
        assert db.scalars(select(Organization)).all() == []
        assert (
            db.execute(
                update(Membership).where(Membership.organization_id == org_a).values(role="hr")
            ).rowcount
            == 0
        )
        assert (
            db.execute(delete(Membership).where(Membership.organization_id == org_b)).rowcount == 0
        )
        db.rollback()
        tenant_context(db, "", identifier())
        assert db.scalars(select(Membership)).all() == []
        tenant_context(db, org_a, user)
        assert {row.organization_id for row in db.scalars(select(Membership))} == {org_a}


def test_live_self_membership_discovery_cannot_insert_memberships(postgres):
    engine, org_a, _, user = postgres
    with Session(engine) as db:
        tenant_context(db, "", user)
        db.add(
            Membership(
                organization_id=org_a,
                user_id=identifier(),
                role="owner",
                email="forbidden@example.invalid",
            )
        )
        with pytest.raises(DBAPIError):
            db.flush()
        db.rollback()


@pytest.mark.parametrize("change", ["issuer", "organization"])
def test_live_invitation_acceptance_rechecks_cached_authority(postgres, change):
    from app.auth import Identity
    from app.services import accept_invitation, invitation
    from fastapi import HTTPException

    engine, _, _, _ = postgres
    org, owner, recipient = identifier(), identifier(), identifier()
    with Session(engine) as db:
        tenant_context(db, org, owner)
        db.add(Organization(id=org, name="Invitation freshness fixture"))
        db.flush()
        db.add(
            Membership(
                organization_id=org, user_id=owner, email="issuer@example.invalid", role="owner"
            )
        )
        db.commit()
        tenant_context(db, org, owner)
        record, token = invitation(
            db, Principal(owner, org, "owner"), "recipient@example.invalid", "hr"
        )
        db.commit()
        tenant_context(db, org, owner)
        assert db.get(Membership, (org, owner)).active
        assert db.get(Organization, org).status == "active"
        with Session(engine) as revocation:
            tenant_context(revocation, org, owner)
            if change == "issuer":
                revocation.execute(
                    update(Membership)
                    .where(Membership.organization_id == org, Membership.user_id == owner)
                    .values(active=False)
                )
            else:
                revocation.execute(
                    update(Organization).where(Organization.id == org).values(status="suspended")
                )
            revocation.commit()
        with pytest.raises(HTTPException) as error:
            accept_invitation(
                db,
                Principal(recipient, org, ""),
                Identity(recipient, "recipient@example.invalid"),
                token,
            )
        assert error.value.status_code == (400 if change == "issuer" else 403)
        assert db.get(Membership, (org, recipient)) is None
        db.rollback()


def test_live_private_ocr_ciphertext_and_tenant_boundary(postgres, monkeypatch):
    from app.core.config import settings
    from app.document_ocr import Suggestions, decrypt, encrypt
    from cryptography.fernet import Fernet
    from pydantic import SecretStr

    engine, org_a, org_b, user = postgres
    monkeypatch.setattr(settings(), "document_ocr_key", SecretStr(Fernet.generate_key().decode()))
    with Session(engine) as db:
        tenant_context(db, org_a, user)
        employee = db.scalar(select(Employee))
        record = IdentityDocument(
            id=identifier(),
            organization_id=org_a,
            employee_id=employee.id,
            storage_key=f"{org_a}/{employee.id}/{identifier()}",
            media_type="image/png",
            digest="0" * 64,
            expires_at=now() + timedelta(days=1),
            ocr_status="completed",
        )
        record.ocr_ciphertext = encrypt(
            record, Suggestions(suggested_name="Synthetic Tester", engine="fixture")
        )
        db.add(record)
        db.flush()
        assert "Synthetic" not in db.scalar(
            text("SELECT ocr_ciphertext FROM identity_documents WHERE id=:id"), {"id": record.id}
        )
        assert decrypt(record).suggested_name == "Synthetic Tester"
        tenant_context(db, org_b, user)
        assert db.scalar(select(IdentityDocument).where(IdentityDocument.id == record.id)) is None
        tenant_context(db, org_a, user)
        # Existing tenant composite FK remains enforced after the additive migration.
        foreign = db.scalar(
            text("SELECT id FROM employees WHERE organization_id=:org"), {"org": org_b}
        )
        assert foreign is None
        db.rollback()


def test_live_normalized_context_filters_rls_and_immutable_observations(postgres):
    from app.models import Anomaly

    engine, org_a, org_b, user = postgres
    with Session(engine) as db:
        tenant_context(db, org_a, user)
        record = SecurityEvent(
            id=identifier(),
            organization_id=org_a,
            source_id=identifier(),
            occurred_at=now(),
            actor_id=user,
            category="device",
            action="observed",
            result="success",
            context={
                "source": {"kind": "device", "name": "fixture"},
                "device": {"new_device": True},
            },
        )
        db.add(record)
        db.flush()
        anomaly = Anomaly(
            organization_id=org_a,
            event_id=record.id,
            rule="new_device",
            weight=15,
            explanation="Reported fixture only",
        )
        db.add(anomaly)
        db.flush()
        query = select(SecurityEvent).where(
            SecurityEvent.context["source"]["kind"].as_string() == "device"
        )
        assert record.id in {row.id for row in db.scalars(query)}
        tenant_context(db, org_b, user)
        assert record.id not in {row.id for row in db.scalars(query)}
        tenant_context(db, org_a, user)
        for model, identity in ((SecurityEvent, record.id), (Anomaly, anomaly.id)):
            with pytest.raises(DBAPIError) as error, db.begin_nested():
                db.execute(update(model).where(model.id == identity).values(id=identity))
            assert (
                error.value.orig.sqlstate == "P0001"
            )  # Trigger, even though this test role has UPDATE.
        db.rollback()


def test_live_audit_trigger_and_transaction_context_reset(postgres):
    engine, org_a, _, user = postgres
    barrier = Barrier(2)

    def append():
        with Session(engine) as db:
            tenant_context(db, org_a, user)
            db.add(Outbox(organization_id=org_a, topic="concurrent.fixture", payload={}))
            db.flush()  # Holds an organization FK key-share lock before audit serialization.
            barrier.wait(timeout=10)
            audit(db, Principal(user, org_a, "junior_developer"), "concurrent.fixture", org_a)
            db.commit()

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(append) for _ in range(2)]
        for future in futures:
            future.result(timeout=20)
    with Session(engine) as db:
        tenant_context(db, org_a, user)
        assert db.scalars(select(AuditSeal.position).order_by(AuditSeal.position)).all() == [1, 2]
    with engine.connect() as connection:
        with connection.begin():
            connection.execute(
                text("SELECT set_config('mesh.organization_id', :org, true)"), {"org": org_a}
            )
            assert connection.scalar(text("SELECT count(*) FROM employees")) >= 1
        with connection.begin():
            assert connection.scalar(text("SELECT count(*) FROM employees")) == 0
    with Session(engine) as db:
        tenant_context(db, org_a, user)
        row = db.scalar(select(AuditLog))
        row.action = "tampered"
        with pytest.raises(DBAPIError):
            db.flush()
        db.rollback()


def test_live_risk_rls_composite_fk_and_append_only_snapshots(postgres):
    engine, org_a, org_b, user = postgres
    with Session(engine) as db:
        tenant_context(db, org_a, user)
        policy = RiskPolicy(
            organization_id=org_a,
            version=1,
            created_by=user,
            algorithm_version="fixture",
            weights={},
            thresholds={},
        )
        db.add(policy)
        db.flush()
        record = RiskAssessment(
            organization_id=org_a,
            policy_id=policy.id,
            requested_by=user,
            request_key=identifier(),
            request_digest="0" * 64,
            window_start=now(),
            window_end=now(),
            synthetic=False,
            result={},
        )
        db.add(record)
        db.flush()
        assert {item.organization_id for item in db.scalars(select(RiskPolicy))} == {org_a}
        assert (
            db.scalars(select(RiskAssessment).where(RiskAssessment.organization_id == org_b)).all()
            == []
        )
        for statement in (
            update(RiskPolicy).where(RiskPolicy.id == policy.id).values(version=2),
            delete(RiskPolicy).where(RiskPolicy.id == policy.id),
            update(RiskAssessment)
            .where(RiskAssessment.id == record.id)
            .values(result={"tampered": True}),
            delete(RiskAssessment).where(RiskAssessment.id == record.id),
        ):
            with pytest.raises(DBAPIError) as error, db.begin_nested():
                db.execute(statement)
            assert error.value.orig.sqlstate == "P0001"
        tenant_context(db, org_b, user)
        foreign = RiskPolicy(
            organization_id=org_b,
            version=1,
            created_by=user,
            algorithm_version="fixture",
            weights={},
            thresholds={},
        )
        db.add(foreign)
        db.flush()
        tenant_context(db, org_a, user)
        with pytest.raises(DBAPIError) as error, db.begin_nested():
            db.add(
                RiskAssessment(
                    organization_id=org_a,
                    policy_id=foreign.id,
                    requested_by=user,
                    request_key=identifier(),
                    request_digest="0" * 64,
                    window_start=now(),
                    window_end=now(),
                    synthetic=False,
                    result={},
                )
            )
            db.flush()
        assert error.value.orig.sqlstate == "23503"
        protected = SecurityEvent(
            organization_id=org_a,
            source_id=identifier(),
            occurred_at=now() - timedelta(days=45),
            actor_id=user,
            category="api",
            action="fixture",
            result="success",
            count=1,
            synthetic=False,
        )
        db.add(protected)
        db.add(
            RiskAssessment(
                organization_id=org_a,
                policy_id=policy.id,
                requested_by=user,
                request_key=identifier(),
                request_digest="0" * 64,
                window_start=now() - timedelta(days=46),
                window_end=now() - timedelta(days=44),
                synthetic=False,
                result={},
            )
        )
        db.flush()
        assert db.scalar(text("SELECT public.mesh_retire_telemetry(30,100)")) == 0
        assert (
            db.scalar(select(SecurityEvent.id).where(SecurityEvent.id == protected.id))
            == protected.id
        )


def test_live_cost_retries_are_serialized_and_actor_foreign_key_is_tenant_bound(postgres):
    from app.enterprise_schemas import CostInput
    from app.finance import record_cost
    from app.models import CostRecord
    from sqlalchemy import func

    engine, org_a, org_b, user = postgres
    actor = identifier()
    with Session(engine) as db:
        tenant_context(db, org_a, user)
        db.add(
            Membership(
                organization_id=org_a, user_id=actor, email=actor + "@example.invalid", role="owner"
            )
        )
        db.commit()
    key = identifier()
    gate = Barrier(2)

    def submit(amount):
        with Session(engine, expire_on_commit=False) as db:
            tenant_context(db, org_a, actor)
            gate.wait(timeout=10)
            row = record_cost(
                db,
                Principal(actor, org_a, "owner"),
                CostInput(
                    request_key=key,
                    period="2026-10",
                    department="Synthetic",
                    category="cloud",
                    currency="INR",
                    amount=amount,
                ),
            )
            db.commit()
            return row.id

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(submit, ["10", "10.00"]))
    assert results[0] == results[1]
    with Session(engine) as db:
        tenant_context(db, org_a, actor)
        assert (
            db.scalar(
                select(func.count()).select_from(CostRecord).where(CostRecord.request_key == key)
            )
            == 1
        )
        assert (
            db.scalar(
                select(func.count())
                .select_from(AuditLog)
                .where(AuditLog.target_id == results[0], AuditLog.action == "finance.cost.recorded")
            )
            == 1
        )
        tenant_context(db, org_b, user)
        with pytest.raises(DBAPIError) as error, db.begin_nested():
            db.add(
                CostRecord(
                    organization_id=org_b,
                    request_key=identifier(),
                    request_digest="a" * 64,
                    recorded_by=actor,
                    period="2026-10",
                    department="Synthetic",
                    category="cloud",
                    currency="INR",
                    amount=1,
                )
            )
            db.flush()
        assert error.value.orig.sqlstate == "23503"


def test_live_rehire_keeps_access_revoked_until_owner_attestation_and_blocks_old_grants(postgres):
    from uuid import UUID

    from app.auth import Identity, principal
    from app.devtrack import project_access
    from app.enterprise_api import lifecycle_approve
    from app.enterprise_schemas import Decision, LifecycleInput
    from app.hr import execute_lifecycle, propose_lifecycle
    from app.models import Project, ProjectMember
    from app.rehire import RehireActivation, activate_rehire
    from fastapi import HTTPException

    engine, org_a, _, user = postgres
    hr, owner = identifier(), identifier()
    with Session(engine) as db:
        tenant_context(db, org_a, hr)
        for uid, role in ((hr, "hr"), (owner, "owner")):
            db.add(
                Membership(
                    organization_id=org_a, user_id=uid, email=uid + "@example.invalid", role=role
                )
            )
        employee = db.scalar(
            select(Employee).where(Employee.organization_id == org_a, Employee.user_id == user)
        )
        employee.verification_status = "approved"
        db.flush()
        hr_p, owner_p = Principal(hr, org_a, "hr"), Principal(owner, org_a, "owner")
        prior = propose_lifecycle(
            db, hr_p, LifecycleInput(employee_id=UUID(employee.id), kind="offboarding")
        )
        lifecycle_approve(UUID(prior.id), Decision(decision="approved"), db, owner_p)
        execute_lifecycle(db, hr_p, prior.id)
        plan = propose_lifecycle(
            db,
            hr_p,
            LifecycleInput(
                employee_id=UUID(employee.id),
                kind="rehire",
                role="junior_developer",
                department="Synthetic rehire",
            ),
        )
        lifecycle_approve(UUID(plan.id), Decision(decision="approved"), db, owner_p)
        execute_lifecycle(db, hr_p, plan.id)
        assert not db.get(Membership, (org_a, user)).active
        project = Project(
            organization_id=org_a, proposer_id=user, name="Old scope", description="Synthetic"
        )
        db.add(project)
        db.flush()
        db.add(
            ProjectMember(organization_id=org_a, project_id=project.id, user_id=user, manager=True)
        )
        db.flush()
        activate_rehire(
            db,
            owner_p,
            plan.id,
            RehireActivation(
                reference="synthetic-provider-session-revocation-ticket",
                provider_sessions_revoked=True,
                external_access_reviewed=True,
            ),
        )
        db.flush()
        assert db.get(Membership, (org_a, user)).active
        assert not db.scalars(
            select(ProjectMember).where(
                ProjectMember.organization_id == org_a, ProjectMember.user_id == user
            )
        ).all()
        with pytest.raises(HTTPException) as error:
            principal(
                Identity(user, user + "@example.invalid", issued_at=now() - timedelta(minutes=1)),
                db,
                UUID(org_a),
            )
        assert error.value.status_code == 401
        fresh = principal(
            Identity(user, user + "@example.invalid", issued_at=now() + timedelta(seconds=1)),
            db,
            UUID(org_a),
        )
        with pytest.raises(HTTPException) as error:
            project_access(db, fresh, project.id)
        assert error.value.status_code == 404
        db.rollback()


def test_live_provisioning_post_intent_commits_before_http_and_recovers_without_duplicate_creation(
    postgres, monkeypatch
):
    from uuid import UUID

    from app import provision_worker
    from app.core.config import SCIMBinding, settings
    from app.enterprise_api import lifecycle_approve
    from app.enterprise_schemas import Decision, LifecycleInput
    from app.hr import execute_lifecycle, propose_lifecycle
    from app.models import IntegrationAccount
    from app.scim_provisioning import ProvisioningSCIMClient
    from fastapi import HTTPException
    from sqlalchemy.orm import sessionmaker

    engine, org_a, _, _ = postgres
    hr, owner, user = identifier(), identifier(), identifier()
    factory = sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(provision_worker, "SessionFactory", factory)
    monkeypatch.setattr(
        settings(),
        "scim_bindings",
        {
            org_a: SCIMBinding(
                base_url="https://synthetic-scim.example.invalid/v2",
                token="fixture-not-a-live-provider-key",
                allow_provisioning=True,
            )
        },
    )
    with factory.begin() as db:
        tenant_context(db, org_a, hr)
        for uid, role in ((hr, "hr"), (owner, "owner"), (user, "junior_developer")):
            db.add(
                Membership(
                    organization_id=org_a, user_id=uid, email=uid + "@example.invalid", role=role
                )
            )
        db.flush()
        employee = Employee(
            organization_id=org_a,
            user_id=user,
            name="Synthetic provisioning",
            department="Verification",
            status="onboarding",
            verification_status="approved",
        )
        db.add(employee)
        db.flush()
        plan = propose_lifecycle(
            db,
            Principal(hr, org_a, "hr"),
            LifecycleInput(employee_id=UUID(employee.id), kind="onboarding", provision_scim=True),
        )
        lifecycle_approve(
            UUID(plan.id), Decision(decision="approved"), db, Principal(owner, org_a, "owner")
        )
        execute_lifecycle(db, Principal(hr, org_a, "hr"), plan.id)
        message = db.scalar(
            select(Outbox).where(
                Outbox.organization_id == org_a,
                Outbox.topic == provision_worker.TOPIC,
                Outbox.payload["plan_id"].as_string() == plan.id,
            )
        )
        message_id, plan_id = message.id, plan.id
    remote, creates = None, []

    def create(*args):
        nonlocal remote
        with factory() as check:
            tenant_context(check, org_a, "provisioning-worker")
            assert check.get(Outbox, message_id).payload["creation_sent"] is True
        creates.append(True)
        remote = {"id": "synthetic-created-user", "active": False}
        raise HTTPException(503, "Simulated response loss after remote creation")

    monkeypatch.setattr(ProvisioningSCIMClient, "find", lambda *args, **kwargs: remote)
    monkeypatch.setattr(ProvisioningSCIMClient, "create_inactive", create)
    assert provision_worker.run_once(org_a)
    with factory.begin() as db:
        tenant_context(db, org_a, "provisioning-worker")
        message = db.get(Outbox, message_id)
        assert message.payload["creation_sent"] is True and message.status == "pending"
        message.available_at = now() - timedelta(seconds=1)
    assert provision_worker.run_once(org_a)
    with factory() as db:
        tenant_context(db, org_a, "provisioning-worker")
        assert len(creates) == 1 and db.get(Outbox, message_id).status == "delivered"
        assert (
            db.get(LifecyclePlan, plan_id).proposed["provisioning"]["state"] == "verified_inactive"
        )
        assert (
            db.scalar(
                select(IntegrationAccount.id).where(
                    IntegrationAccount.organization_id == org_a, IntegrationAccount.user_id == user
                )
            )
            is not None
        )


def test_live_correlation_policy_scope_immutability_and_retained_incident_snapshot(postgres):
    from app.correlation import CorrelationConfig, PolicyChange, create_policy
    from app.models import CorrelationPolicy, Incident
    from app.schemas import EventInput
    from app.vader import ingest
    from fastapi import HTTPException
    from sqlalchemy.exc import IntegrityError

    engine, org_a, org_b, user = postgres
    with Session(engine) as db:
        tenant_context(db, org_a, user)
        db.get(Membership, (org_a, user)).role = "security_analyst"
        db.flush()
        actor = Principal(user, org_a, "security_analyst")
        policy = create_policy(
            db,
            actor,
            PolicyChange(
                expected_version=0,
                configuration=CorrelationConfig(
                    minimum_categories=2, minimum_events=2, link_mode="session"
                ),
            ),
        )
        for category, result, count in (
            ("authentication", "failure", 8),
            ("download", "success", 200),
        ):
            outcome = ingest(
                db,
                actor,
                EventInput(
                    source_id=identifier(),
                    actor_id=user,
                    category=category,
                    action="synthetic",
                    result=result,
                    count=count,
                    occurred_at=now(),
                    session_id="synthetic-session",
                ),
            )
        assert outcome.correlation_status == "matched"
        incident = db.get(Incident, outcome.incident_id)
        assert (
            incident.correlation_policy_id == policy.id
            and incident.correlation_snapshot["policy_version"] == 1
        )
        for mutation in (
            update(CorrelationPolicy)
            .where(CorrelationPolicy.id == policy.id)
            .values(configuration={}),
            delete(CorrelationPolicy).where(CorrelationPolicy.id == policy.id),
            update(Incident).where(Incident.id == incident.id).values(correlation_snapshot={}),
        ):
            with pytest.raises(DBAPIError) as error, db.begin_nested():
                db.execute(mutation)
            assert error.value.orig.sqlstate == "P0001"
        incident.status = "triaged"
        db.flush()
        with pytest.raises(HTTPException) as error:
            create_policy(
                db, actor, PolicyChange(expected_version=0, configuration=CorrelationConfig())
            )
        assert error.value.status_code == 409
        tenant_context(db, org_b, user)
        assert (
            db.scalar(select(CorrelationPolicy.id).where(CorrelationPolicy.id == policy.id)) is None
        )
        with pytest.raises(IntegrityError) as error, db.begin_nested():
            db.add(
                Incident(
                    organization_id=org_b,
                    actor_id=user,
                    fingerprint=identifier(),
                    event_ids=[],
                    risk=0,
                    explanation="Synthetic",
                    correlation_policy_id=policy.id,
                    correlation_snapshot={"policy_version": 1},
                )
            )
            db.flush()
        assert error.value.orig.sqlstate == "23503"
        db.rollback()


@pytest.mark.parametrize("revocation", ["role", "inactive"])
def test_live_org_status_rechecks_owner_after_concurrent_revocation(
    postgres, monkeypatch, revocation
):
    from threading import Event
    from uuid import UUID

    from app import account_api
    from app.account_api import OrganizationStatus, organization_status
    from app.auth import Identity
    from app.services import lock_tenant
    from fastapi import HTTPException

    engine, org, _, user = postgres
    ready, waiting = Event(), Event()
    with Session(engine) as db:
        tenant_context(db, org, user)
        member = db.get(Membership, (org, user))
        previous_role, previous_active = member.role, member.active
        previous_status = db.get(Organization, org).status
        member.role, member.active = "owner", True
        db.commit()

    def gated_lock(db, organization):
        waiting.set()
        return lock_tenant(db, organization)

    monkeypatch.setattr(account_api, "lock_tenant", gated_lock)

    def revoke():
        with Session(engine) as db:
            tenant_context(db, org, user)
            lock_tenant(db, org)
            member = db.get(Membership, (org, user), with_for_update=True)
            if revocation == "role":
                member.role = "junior_developer"
            else:
                member.active = False
            db.flush()
            ready.set()
            assert waiting.wait(15), "Status request did not reach the tenant lock"
            db.commit()

    def change_status():
        with Session(engine) as db:
            tenant_context(db, org, user)
            db.execute(text("SET LOCAL lock_timeout='15s'"))
            try:
                organization_status(
                    OrganizationStatus(status="suspended"),
                    Identity(user, user + "@example.org", "aal2"),
                    db,
                    UUID(org),
                )
                db.commit()
                return 200
            except HTTPException as error:
                db.rollback()
                return error.status_code

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            revoker = pool.submit(revoke)
            assert ready.wait(15)
            request = pool.submit(change_status)
            assert request.result(timeout=30) == 403
            revoker.result(timeout=30)
        with Session(engine) as db:
            tenant_context(db, org, user)
            assert db.get(Organization, org).status == previous_status
            assert (
                db.scalar(
                    select(AuditLog.id).where(
                        AuditLog.organization_id == org, AuditLog.action == "organization.suspended"
                    )
                )
                is None
            )
    finally:
        waiting.set()
        with Session(engine) as db:
            tenant_context(db, org, user)
            lock_tenant(db, org)
            member = db.get(Membership, (org, user), with_for_update=True)
            member.role, member.active = previous_role, previous_active
            db.get(Organization, org).status = previous_status
            db.commit()


def test_live_concurrent_business_requests_do_not_leak_tenant_or_role_context(postgres):
    from app.auth import Identity, identity
    from app.core.db import session
    from app.main import app
    from app.models import Finding, Repository
    from fastapi import HTTPException, Request
    from fastapi.testclient import TestClient

    engine, _, _, _ = postgres
    tenants = [identifier(), identifier()]
    actors, repositories, finding_ids = {}, {}, {}
    with Session(engine) as db:
        for org in tenants:
            tenant_context(db, org, "fixture-setup")
            db.add(Organization(id=org, name="Concurrent synthetic tenant"))
            db.flush()
            for role in ("hr", "owner", "security_analyst"):
                user = identifier()
                actors[org, role] = user
                db.add(
                    Membership(
                        organization_id=org,
                        user_id=user,
                        email=user + "@example.invalid",
                        role=role,
                    )
                )
            db.flush()
            db.add(
                Employee(
                    organization_id=org,
                    user_id=actors[org, "hr"],
                    name="Concurrent-" + org,
                    department="Synthetic",
                    status="active",
                )
            )
            repo = Repository(
                organization_id=org, full_name="synthetic/concurrent-" + org, installation_id=1
            )
            db.add(repo)
            db.flush()
            observation = Finding(
                organization_id=org,
                repository_id=repo.id,
                scanner="bandit",
                rule_id="synthetic-" + org,
                file_path="synthetic.py",
                line=1,
                severity="high",
            )
            db.add(observation)
            db.flush()
            repositories[org], finding_ids[org] = repo.id, observation.id
        db.commit()

    token_users = {"Bearer synthetic-" + user: user for user in actors.values()}

    def synthetic_identity(request: Request):
        user = token_users.get(request.headers.get("authorization", ""))
        if user is None:
            raise HTTPException(401, "Synthetic test identity required")
        return Identity(user, user + "@example.invalid")

    def transaction():
        with Session(engine) as db:
            db.execute(text("SET LOCAL statement_timeout='5s'"))
            db.execute(text("SET LOCAL lock_timeout='3s'"))
            try:
                yield db
                db.commit()
            except Exception:
                db.rollback()
                raise

    original = dict(app.dependency_overrides)
    app.dependency_overrides[identity] = synthetic_identity
    app.dependency_overrides[session] = transaction
    cases = []
    for index, org in enumerate(tenants):
        other = tenants[1 - index]
        cases.extend(
            [
                (org, actors[org, "hr"], "/api/v1/employees", 200, "employees"),
                (
                    org,
                    actors[org, "security_analyst"],
                    f"/api/v1/repositories/{repositories[org]}/findings",
                    200,
                    "findings",
                ),
                (org, actors[org, "owner"], "/api/v1/finance/summary", 200, "finance"),
                (org, actors[org, "security_analyst"], "/api/v1/employees", 403, "denied"),
                (other, actors[org, "hr"], "/api/v1/employees", 403, "denied"),
                (
                    org,
                    actors[org, "security_analyst"],
                    f"/api/v1/repositories/{repositories[other]}/findings",
                    404,
                    "denied",
                ),
            ]
        )
    try:
        with TestClient(app, raise_server_exceptions=False) as client:

            def request(case):
                org, user, path, status, kind = case
                response = client.get(
                    path,
                    headers={"Authorization": "Bearer synthetic-" + user, "X-Organization-ID": org},
                )
                assert response.status_code == status, (status, response.status_code, response.text)
                assert response.headers["cache-control"] == "no-store"
                if kind == "employees":
                    assert [row["name"] for row in response.json()] == ["Concurrent-" + org]
                elif kind == "findings":
                    assert [row["id"] for row in response.json()] == [finding_ids[org]]
                elif kind == "finance":
                    assert response.json()["currency"] == "INR"
                return response.headers["x-request-id"]

            with ThreadPoolExecutor(max_workers=4) as executor:
                requests = list(executor.map(request, cases * 8))
        assert len(requests) == 96 and len(set(requests)) == 96
        with Session(engine) as db:
            assert db.scalars(select(Employee)).all() == []
            assert (
                db.scalar(text("SELECT nullif(current_setting('mesh.organization_id',true),'')"))
                is None
            )
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(original)


def test_live_ai_aggregate_admission_and_currency_summary(postgres, monkeypatch):
    from decimal import Decimal

    from app.ai import Generation, Insight, generate
    from app.ai_usage import usage_summary
    from app.core.config import AIUsagePolicy, settings
    from app.models import AIUsage
    from fastapi import HTTPException

    engine, _, org_b, _ = postgres
    org_a, user = identifier(), identifier()
    # A genuinely committed owner is required by independent accounting reads.
    # Every record belongs to the disposable test database; no hosted data used.
    with Session(engine) as setup:
        tenant_context(setup, org_a, user)
        setup.add(Organization(id=org_a, name="Synthetic AI accounting tenant"))
        setup.flush()
        setup.add(
            Membership(
                organization_id=org_a, user_id=user, email=user + "@example.invalid", role="owner"
            )
        )
        setup.commit()
    config = settings()
    monkeypatch.setattr(config, "ai_provider", "gateway")
    monkeypatch.setattr(config, "ai_model", "synthetic-model")
    monkeypatch.setattr(
        config,
        "ai_policies",
        {
            org_a: AIUsagePolicy(
                provider="gateway",
                model="synthetic-model",
                currency="USD",
                input_price_per_million="2.5",
                output_price_per_million="5",
                monthly_requests=1,
                monthly_cost_limit="100",
            )
        },
    )
    calls = []

    class FixtureProvider:
        def generate(self, purpose, context):
            calls.append(True)
            return Generation(
                Insight(summary="Synthetic", recommendations=[], limitations=["Fixture"]),
                "gateway",
                100,
                50,
            )

    with Session(engine) as db:
        tenant_context(db, org_b, user)
        db.add(
            AIUsage(
                organization_id=org_b,
                provider="gateway",
                purpose="owner",
                input_units=999999,
                output_units=999999,
            )
        )
        db.flush()
        tenant_context(db, org_a, user)
        actor = Principal(user, org_a, "owner")
        result = generate(db, actor, "owner", {"records": 1}, FixtureProvider())
        assert result["usage"]["estimated_cost"] == Decimal("0.000500")
        db.flush()
        summary = usage_summary(db, actor, now().strftime("%Y-%m"), 50, 0)
        assert summary.total_groups == 1 and summary.groups[0].recorded_requests == 1
        assert summary.groups[0].known_estimated_cost == Decimal("0.000500")
        assert usage_summary(db, actor, summary.month, 50, 99).total_groups == 1
        with pytest.raises(HTTPException) as error:
            generate(db, actor, "owner", {"records": 1}, FixtureProvider())
        assert error.value.status_code == 429 and len(calls) == 1
        db.rollback()


def test_live_finding_identities_are_immutable_scoped_and_preserve_history(postgres):
    from app.finding_identity import identities, index_observations
    from app.models import Finding, FindingIdentity, Repository
    from sqlalchemy.exc import IntegrityError

    engine, org_a, org_b, user = postgres
    with Session(engine) as db:
        tenant_context(db, org_a, user)
        member = db.get(Membership, (org_a, user))
        member.role = "security_analyst"
        repo = Repository(
            organization_id=org_a, full_name="synthetic/identity-" + identifier(), installation_id=1
        )
        other = Repository(
            organization_id=org_a,
            full_name="synthetic/identity-other-" + identifier(),
            installation_id=1,
        )
        db.add_all([repo, other])
        db.flush()
        first_time = now() - timedelta(hours=1)
        rows = [
            Finding(
                organization_id=org_a,
                repository_id=repo.id,
                scanner="bandit",
                rule_id="B307",
                severity="high",
                file_path="a.py",
                line=1,
                status=state,
                created_at=when,
            )
            for state, when in (("open", first_time), ("resolved", now()))
        ]
        db.add_all(rows)
        db.flush()
        actor = Principal(user, org_a, "security_analyst")
        assert index_observations(db, actor, repo.id, 1)["remaining_unindexed"] == 1
        assert index_observations(db, actor, repo.id, 5)["remaining_unindexed"] == 0
        assert rows[0].identity_id == rows[1].identity_id
        group = identities(db, actor, repo.id, 10, 0)["groups"][0]
        assert group["observations"] == 2 and group["distinct_scans"] == 0
        assert group["observations_without_scan_provenance"] == 2
        assert group["latest_status"] == "resolved" and group["statuses"]["open"] == 1
        identity_id = rows[0].identity_id
        for mutation in (
            update(FindingIdentity)
            .where(FindingIdentity.id == identity_id)
            .values(algorithm_version="tampered"),
            delete(FindingIdentity).where(FindingIdentity.id == identity_id),
        ):
            with pytest.raises(DBAPIError) as error, db.begin_nested():
                db.execute(mutation)
            assert error.value.orig.sqlstate == "P0001"
        with pytest.raises(IntegrityError) as error, db.begin_nested():
            db.add(
                Finding(
                    organization_id=org_a,
                    repository_id=other.id,
                    scanner="bandit",
                    rule_id="B307",
                    severity="high",
                    file_path="a.py",
                    line=1,
                    identity_id=identity_id,
                )
            )
            db.flush()
        assert error.value.orig.sqlstate == "23503"
        tenant_context(db, org_b, user)
        assert (
            db.scalar(select(FindingIdentity.id).where(FindingIdentity.id == identity_id)) is None
        )
        db.rollback()


def test_live_finding_provenance_cannot_cross_tenant_repository_or_commit(postgres):
    from app.models import Finding, Repository, ScanJob
    from sqlalchemy.exc import IntegrityError

    engine, org_a, org_b, user = postgres
    repositories, jobs = [], []
    with Session(engine) as db:
        for org, suffix in ((org_a, "a"), (org_a, "b"), (org_b, "c")):
            tenant_context(db, org, user)
            repo = Repository(
                organization_id=org,
                full_name="synthetic/provenance-" + identifier(),
                installation_id=1,
            )
            db.add(repo)
            db.flush()
            job = ScanJob(
                organization_id=org,
                repository_id=repo.id,
                requested_by=user,
                request_key=identifier(),
                commit_sha=suffix * 40,
            )
            db.add(job)
            db.flush()
            repositories.append(repo)
            jobs.append(job)
        tenant_context(db, org_a, user)
        valid = Finding(
            organization_id=org_a,
            repository_id=repositories[0].id,
            scanner="osv",
            rule_id="OSV-SYNTHETIC",
            severity="info",
            file_path="dependency-manifest",
            line=1,
            scan_job_id=jobs[0].id,
            commit_sha=jobs[0].commit_sha,
            dependency={"name": "synthetic", "ecosystem": "PyPI", "version": "1"},
        )
        db.add(valid)
        db.flush()
        for index, commit in ((1, jobs[1].commit_sha), (2, jobs[2].commit_sha), (0, "f" * 40)):
            with pytest.raises(IntegrityError) as error, db.begin_nested():
                db.add(
                    Finding(
                        organization_id=org_a,
                        repository_id=repositories[0].id,
                        scanner="bandit",
                        rule_id="B307",
                        severity="high",
                        file_path="a.py",
                        line=1,
                        scan_job_id=jobs[index].id,
                        commit_sha=commit,
                    )
                )
                db.flush()
            assert error.value.orig.sqlstate == "23503"
        with pytest.raises(IntegrityError) as error, db.begin_nested():
            db.add(
                Finding(
                    organization_id=org_a,
                    repository_id=repositories[0].id,
                    scanner="bandit",
                    rule_id="B307",
                    severity="high",
                    file_path="a.py",
                    line=1,
                    scan_job_id=jobs[0].id,
                    commit_sha=None,
                )
            )
            db.flush()
        assert error.value.orig.sqlstate == "23514"
        with pytest.raises(IntegrityError) as error, db.begin_nested():
            db.execute(update(ScanJob).where(ScanJob.id == jobs[0].id).values(commit_sha="d" * 40))
        assert error.value.orig.sqlstate == "23503"
        db.rollback()


# This fragment is appended into the existing opt-in PostgreSQL module.


@pytest.fixture
def ai_postgres(postgres, monkeypatch):
    from app.ai_accounting_pool import close
    from app.core.config import AIUsagePolicy, settings

    existing, _, _, _ = postgres
    close()
    parent = create_engine(existing.url, pool_size=1, max_overflow=0, pool_timeout=2)
    org, user = identifier(), identifier()
    with Session(parent) as db:
        tenant_context(db, org, user)
        db.add(Organization(id=org, name="Synthetic durable AI test"))
        db.flush()
        db.add(
            Membership(
                organization_id=org, user_id=user, email=user + "@example.invalid", role="owner"
            )
        )
        db.commit()
    config = settings()
    policy = AIUsagePolicy(
        provider="gateway",
        model="synthetic-ledger-model",
        currency="USD",
        input_price_per_million="2.5",
        output_price_per_million="5",
        monthly_requests=10,
        monthly_cost_limit="1000",
    )
    monkeypatch.setattr(config, "ai_provider", "gateway")
    monkeypatch.setattr(config, "ai_model", policy.model)
    monkeypatch.setattr(config, "ai_url", "https://fixture.invalid/generate")
    monkeypatch.setattr(config, "ai_policies", {org: policy})
    try:
        yield parent, Principal(user, org, "owner"), policy
    finally:
        close()
        parent.dispose()


def test_live_ai_commits_intent_before_provider_and_survives_caller_rollback_with_saturated_pool(
    ai_postgres,
):
    from app.ai import Generation, Insight, generate
    from app.ai_accounting_pool import engine_for
    from app.models import AIRequest, AIRequestEvent, AIUsage

    parent, actor, _ = ai_postgres
    observed = []

    class ProviderBoundary:
        def generate(self, purpose, context):
            independent = engine_for(parent)
            assert independent is not parent
            with Session(independent) as observer:
                tenant_context(observer, actor.organization_id, actor.user_id)
                receipt = observer.scalar(
                    select(AIRequest).where(AIRequest.organization_id == actor.organization_id)
                )
                assert receipt.status == "dispatched" and receipt.dispatch_token
                assert (
                    observer.scalar(
                        select(Outbox.id).where(
                            Outbox.organization_id == actor.organization_id,
                            Outbox.topic == "verification.ai.rollback",
                        )
                    )
                    is None
                )
                observed.append(receipt.id)
            return Generation(
                Insight(
                    summary="Synthetic", recommendations=[], limitations=["No external provider"]
                ),
                "gateway",
                100,
                50,
            )

    with Session(parent) as caller:
        tenant_context(caller, actor.organization_id, actor.user_id)
        caller.add(
            Outbox(
                organization_id=actor.organization_id,
                topic="verification.ai.rollback",
                payload={"fixture": True},
            )
        )
        caller.flush()
        result = generate(caller, actor, "owner", {"records": 1}, ProviderBoundary())
        caller.rollback()
    assert observed == [result["usage"]["request_id"]]
    with Session(parent) as db:
        tenant_context(db, actor.organization_id, actor.user_id)
        receipt = db.scalar(select(AIRequest).where(AIRequest.id == observed[0]))
        usage = db.scalar(select(AIUsage).where(AIUsage.request_id == receipt.id))
        assert receipt.status == "succeeded" and usage.input_units == 100
        assert (
            db.scalar(
                select(func.count())
                .select_from(AIRequestEvent)
                .where(AIRequestEvent.request_id == receipt.id)
            )
            == 3
        )
        assert (
            db.scalar(select(Outbox.id).where(Outbox.organization_id == actor.organization_id))
            is None
        )


def test_live_ai_ambiguous_failure_survives_rollback_and_blocks_another_model_call(
    ai_postgres, monkeypatch
):
    from app.ai import generate
    from app.core.config import settings
    from app.models import AIRequest, AIUsage
    from fastapi import HTTPException

    parent, actor, policy = ai_postgres
    monkeypatch.setattr(
        settings(),
        "ai_policies",
        {actor.organization_id: policy.model_copy(update={"monthly_requests": 1})},
    )
    calls = []

    class FailingProvider:
        def generate(self, purpose, context):
            calls.append(True)
            raise RuntimeError("private fixture transport error")

    for expected in (503, 429):
        with Session(parent) as caller:
            tenant_context(caller, actor.organization_id, actor.user_id)
            with pytest.raises(HTTPException) as error:
                generate(caller, actor, "owner", {"records": 1}, FailingProvider())
            assert error.value.status_code == expected
            caller.rollback()
    assert len(calls) == 1
    with Session(parent) as db:
        tenant_context(db, actor.organization_id, actor.user_id)
        request = db.scalar(
            select(AIRequest).where(AIRequest.organization_id == actor.organization_id)
        )
        assert request.status == "ambiguous" and request.observed_input_units is None
        assert (
            db.scalar(select(AIUsage.id).where(AIUsage.organization_id == actor.organization_id))
            is None
        )


def test_live_ai_admission_serializes_concurrent_independent_reservations(ai_postgres):
    from app.ai_accounting import SQLAccounting
    from app.ai_accounting_pool import engine_for
    from app.models import AIRequest
    from fastapi import HTTPException

    parent, actor, policy = ai_postgres
    limit = policy.model_copy(update={"monthly_requests": 1})
    barrier = Barrier(2)

    def reserve_one():
        store = SQLAccounting(engine_for(parent), actor)
        barrier.wait(timeout=10)
        try:
            store.reserve("owner", limit, "a" * 64, "b" * 64)
            return 201
        except HTTPException as error:
            return error.status_code

    with ThreadPoolExecutor(max_workers=2) as executor:
        statuses = list(executor.map(lambda _: reserve_one(), range(2)))
    assert sorted(statuses) == [201, 429]
    with Session(parent) as db:
        tenant_context(db, actor.organization_id, actor.user_id)
        assert (
            db.scalar(
                select(func.count())
                .select_from(AIRequest)
                .where(AIRequest.organization_id == actor.organization_id)
            )
            == 1
        )


def test_live_ai_cancellation_reconciliation_fencing_and_immutable_observations(ai_postgres):
    from decimal import Decimal

    from app.ai_accounting import SQLAccounting
    from app.ai_accounting_pool import engine_for
    from app.ai_receipts_schema import ReconciliationInput
    from app.models import AIRequest, AIRequestEvent, AIUsage
    from fastapi import HTTPException

    parent, actor, policy = ai_postgres
    store = SQLAccounting(engine_for(parent), actor)
    clock = [now().replace(day=15, hour=12, minute=0, second=0, microsecond=0)]
    store.clock = lambda: clock[0]
    cancelled = store.reserve("owner", policy, "a" * 64, "b" * 64)
    clock[0] += timedelta(seconds=61)
    assert store.cancel_expired(cancelled.id).status == "cancelled"
    assert store.cancel_expired(cancelled.id).status == "cancelled"
    with pytest.raises(HTTPException) as error:
        store.dispatch(cancelled.id, identifier())
    assert error.value.status_code == 409
    record = store.reserve("owner", policy, "a" * 64, "b" * 64)
    token = identifier()
    store.dispatch(record.id, token)
    store.not_dispatched(record.id, identifier())
    report = ReconciliationInput(
        outcome="charge",
        worker_stopped=True,
        provider_billing_reviewed=True,
        reference="fixture:1",
        input_units=100,
        output_units=50,
        amount="1.25",
        currency="USD",
    )
    with pytest.raises(HTTPException) as error:
        store.reconcile(record.id, report)
    assert error.value.status_code == 409
    clock[0] += timedelta(seconds=91)
    assert store.reconcile(record.id, report).status == "reconciled_charge"
    assert store.reconcile(record.id, report).status == "reconciled_charge"
    store.ambiguous(record.id, token, (200, 70))
    succeeded = store.reserve("owner", policy, "a" * 64, "b" * 64)
    next_token = identifier()
    store.dispatch(succeeded.id, next_token)
    store.succeed(succeeded.id, next_token, "gateway", 100, 50)
    store.succeed(succeeded.id, next_token, "gateway", 100, 50)
    no_charge = store.reserve("owner", policy, "a" * 64, "b" * 64)
    store.dispatch(no_charge.id, identifier())
    clock[0] += timedelta(seconds=91)
    assert (
        store.reconcile(
            no_charge.id,
            ReconciliationInput(
                outcome="no_charge",
                worker_stopped=True,
                provider_billing_reviewed=True,
                reference="fixture:no-charge",
            ),
        ).status
        == "reconciled_no_charge"
    )
    with Session(parent) as db:
        tenant_context(db, actor.organization_id, actor.user_id)
        observed = db.get(AIRequest, record.id)
        assert observed.status == "ambiguous" and observed.observed_cost == Decimal("1.250000")
        free_report = db.get(AIRequest, no_charge.id)
        assert free_report.observed_input_units is None and free_report.observed_cost is None
        kinds = db.scalars(
            select(AIRequestEvent.kind)
            .where(AIRequestEvent.request_id == record.id)
            .order_by(AIRequestEvent.position)
        ).all()
        assert kinds == ["reserved", "dispatched", "reconciled_charge", "late_observation"]
        assert (
            db.scalar(
                select(func.count()).select_from(AIUsage).where(AIUsage.request_id == succeeded.id)
            )
            == 1
        )
        for statement in (
            update(AIRequest).where(AIRequest.id == record.id).values(purpose="hr"),
            update(AIRequest).where(AIRequest.id == record.id).values(dispatch_token=identifier()),
            update(AIRequestEvent)
            .where(AIRequestEvent.request_id == record.id)
            .values(details={"changed": True}),
            update(AIUsage).where(AIUsage.request_id == succeeded.id).values(input_units=999),
        ):
            with pytest.raises(DBAPIError) as error, db.begin_nested():
                db.execute(statement)
            assert error.value.orig.sqlstate == "P0001"
        with pytest.raises(DBAPIError) as error, db.begin_nested():
            db.execute(delete(AIRequest).where(AIRequest.id == record.id))
        assert error.value.orig.sqlstate == "P0001"


def test_live_ai_receipt_rls_and_usage_period_foreign_keys(ai_postgres):
    from app.ai_accounting import SQLAccounting
    from app.ai_accounting_pool import engine_for
    from app.models import AIRequest, AIRequestEvent, AIUsage

    parent, actor, policy = ai_postgres
    store = SQLAccounting(engine_for(parent), actor)
    request = store.reserve("owner", policy, "a" * 64, "b" * 64)
    other = identifier()
    with Session(parent) as db:
        assert db.scalars(select(AIRequest)).all() == []
        assert db.scalars(select(AIRequestEvent)).all() == []
        tenant_context(db, other, actor.user_id)
        db.add(Organization(id=other, name="Synthetic second accounting tenant"))
        db.flush()
        assert db.scalars(select(AIRequest)).all() == []
        assert db.scalars(select(AIRequestEvent)).all() == []
        with pytest.raises(DBAPIError) as error, db.begin_nested():
            db.add(
                AIRequestEvent(
                    organization_id=other,
                    request_id=request.id,
                    actor_id=actor.user_id,
                    position=1,
                    kind="fixture",
                    details={},
                )
            )
            db.flush()
        assert error.value.orig.sqlstate == "23503"
        for organization, period_start in (
            (other, request.period_start),
            (actor.organization_id, request.period_start + timedelta(days=40)),
        ):
            tenant_context(db, organization, actor.user_id)
            with pytest.raises(DBAPIError) as error, db.begin_nested():
                db.add(
                    AIUsage(
                        organization_id=organization,
                        request_id=request.id,
                        admission_period_start=period_start,
                        provider="gateway",
                        purpose="owner",
                        model=policy.model,
                        input_units=1,
                        output_units=1,
                    )
                )
                db.flush()
            assert error.value.orig.sqlstate == "23503"
        db.rollback()


def test_live_cloud_context_rls_immutability_and_envelope_scope(postgres):
    from app.cloud_identity import AWSAccountIdentity
    from app.cloud_normalizer import CloudNormalizer
    from app.models import CloudAssessment

    engine, org_a, org_b, user = postgres
    normalizer = CloudNormalizer(
        org_a, AWSAccountIdentity.from_role("arn:aws:iam::012345678901:role/mesh-reader"), {}, 200
    )
    normalizer.observe("s3", "s3.bucket", native="native-fixture-bucket")
    graph = normalizer.finish([], ["Disposable native PostgreSQL fixture"])
    record_id = graph["envelope"]["assessment_id"]
    with Session(engine) as db:
        tenant_context(db, org_a, user)
        db.add(
            CloudAssessment(
                id=record_id,
                organization_id=org_a,
                findings=[],
                partial=True,
                normalized_context=graph,
            )
        )
        db.commit()
    with Session(engine) as db:
        tenant_context(db, org_b, user)
        assert db.scalar(select(CloudAssessment).where(CloudAssessment.id == record_id)) is None
    with Session(engine) as db:
        tenant_context(db, org_a, user)
        assert (
            db.scalar(
                select(CloudAssessment.normalized_context).where(CloudAssessment.id == record_id)
            )
            == graph
        )
        with pytest.raises(DBAPIError):
            db.execute(
                update(CloudAssessment)
                .where(CloudAssessment.id == record_id)
                .values(normalized_context=None)
            )
        db.rollback()
        tenant_context(db, org_a, user)
        with pytest.raises(DBAPIError):
            db.add(
                CloudAssessment(
                    id=identifier(),
                    organization_id=org_a,
                    findings=[],
                    partial=True,
                    normalized_context=graph,
                )
            )
            db.flush()
        db.rollback()


def test_live_cloud_context_job_link_is_deferred_and_tenant_scoped(postgres):
    from app.cloud_identity import AWSAccountIdentity
    from app.cloud_normalizer import CloudNormalizer
    from app.models import CloudAssessment, CloudAssessmentJob

    engine, org_a, org_b, user = postgres
    for valid in (False, True):
        normalizer = CloudNormalizer(
            org_a,
            AWSAccountIdentity.from_role("arn:aws:iam::012345678901:role/mesh-reader"),
            {},
            200,
        )
        graph = normalizer.finish([], ["Disposable job linkage fixture"])
        record_id, job_id = graph["envelope"]["assessment_id"], identifier()
        graph["envelope"]["source_job_id"] = job_id
        with Session(engine) as db:
            tenant_context(db, org_a, user)
            db.add(
                CloudAssessmentJob(
                    id=job_id, organization_id=org_a, requested_by=user, request_key=identifier()
                )
            )
            db.flush()
            db.add(
                CloudAssessment(
                    id=record_id,
                    organization_id=org_a,
                    findings=[],
                    partial=True,
                    normalized_context=graph,
                )
            )
            db.flush()  # Publication precedes the worker's completion link in this transaction.
            if valid:
                job = db.get(CloudAssessmentJob, job_id)
                job.status, job.assessment_id = "completed", record_id
                db.commit()
            else:
                with pytest.raises(DBAPIError):
                    db.commit()
                db.rollback()


def _billing_fixture(postgres):

    engine, _, _, _ = postgres
    org, user = identifier(), identifier()
    with Session(engine) as db:
        tenant_context(db, org, user)
        db.add(Organization(id=org, name="Disposable billing fixture"))
        db.flush()
        db.add(
            Membership(
                organization_id=org, user_id=user, email=user + "@example.invalid", role="owner"
            )
        )
        db.commit()
    return engine, org, user


def test_live_billing_admission_rls_and_immutable_dispatch(postgres, monkeypatch):
    from uuid import UUID

    from app.billing_collections import request_collection
    from app.core.config import settings
    from app.models import BillingCollection

    engine, org, user = _billing_fixture(postgres)
    monkeypatch.setattr(
        settings(),
        "aws_billing_role_bindings",
        {org: "arn:aws:iam::012345678901:role/mesh-billing"},
    )
    p = Principal(user, org, "owner")
    with Session(engine) as db:
        row = request_collection(
            db, p, request_key=UUID(identifier()), period=now().strftime("%Y-%m")
        )
        key = row.id
        db.commit()
    with Session(engine) as db:
        tenant_context(db, identifier(), user)
        assert db.scalar(select(BillingCollection).where(BillingCollection.id == key)) is None
    with Session(engine) as db:
        tenant_context(db, org, user)
        with pytest.raises(DBAPIError):
            db.execute(
                update(BillingCollection)
                .where(BillingCollection.id == key)
                .values(period="2020-01")
            )
        db.rollback()
        tenant_context(db, org, user)
        row = db.get(BillingCollection, key)
        row.status, row.attempts, row.dispatch_token, row.dispatched_at, row.lease_until = (
            "running",
            1,
            identifier(),
            now(),
            now() + timedelta(minutes=5),
        )
        db.commit()
        tenant_context(db, org, user)
        with pytest.raises(DBAPIError):
            db.execute(
                update(BillingCollection)
                .where(BillingCollection.id == key)
                .values(dispatch_token=identifier())
            )
        db.rollback()
        tenant_context(db, org, user)
        row = db.get(BillingCollection, key)
        row.status, row.lease_until, row.finished_at, row.error_code = (
            "failed",
            None,
            now(),
            "fixture_failure",
        )
        db.commit()
        tenant_context(db, org, user)
        with pytest.raises(DBAPIError):
            db.execute(
                update(BillingCollection)
                .where(BillingCollection.id == key)
                .values(error_code="rewritten")
            )
        db.rollback()


def test_live_billing_concurrent_admission_is_actor_bound_and_single_receipt(postgres, monkeypatch):
    from uuid import UUID

    from app.billing_collections import request_collection
    from app.core.config import settings
    from app.models import BillingCollection

    engine, org, user = _billing_fixture(postgres)
    monkeypatch.setattr(
        settings(),
        "aws_billing_role_bindings",
        {org: "arn:aws:iam::012345678901:role/mesh-billing"},
    )
    key = UUID(identifier())
    barrier = Barrier(2)

    def admit():
        with Session(engine) as db:
            barrier.wait(timeout=10)
            row = request_collection(
                db, Principal(user, org, "owner"), request_key=key, period=now().strftime("%Y-%m")
            )
            result = row.id
            db.commit()
            return result

    with ThreadPoolExecutor(max_workers=2) as pool:
        first, second = list(pool.map(lambda _: admit(), range(2)))
    assert first == second
    with Session(engine) as db:
        tenant_context(db, org, user)
        assert db.scalar(select(func.count()).select_from(BillingCollection)) == 1


def test_live_billing_worker_commits_before_call_and_preserves_scoped_result(postgres, monkeypatch):
    from decimal import Decimal
    from uuid import UUID

    from app.aws_billing import AWSBillingReport, CurrencyCost, ServiceCost, period_bounds
    from app.billing_collections import read_report, request_collection
    from app.billing_worker import run_once
    from app.core.config import settings
    from app.models import BillingCollection
    from sqlalchemy.orm import sessionmaker

    engine, org, user = _billing_fixture(postgres)
    monkeypatch.setattr(
        settings(),
        "aws_billing_role_bindings",
        {org: "arn:aws:iam::012345678901:role/mesh-billing"},
    )
    factory = sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr("app.billing_worker.SessionFactory", factory)
    principal = Principal(user, org, "owner")
    with factory.begin() as db:
        row = request_collection(
            db, principal, request_key=UUID(identifier()), period=now().strftime("%Y-%m")
        )
        key = row.id
    calls = []

    def runner(organization, period):
        with factory() as observer:
            tenant_context(observer, org, user)
            observed = observer.get(BillingCollection, key)
            assert (
                observed.status == "running" and observed.attempts == 1 and observed.dispatch_token
            )
        calls.append(True)
        _, start, end = period_bounds(period, now().date())
        return AWSBillingReport(
            organization_id=organization,
            provider_account_id="012345678901",
            period=period,
            period_start=start,
            period_end=end,
            estimated=True,
            collected_at=now(),
            observations=[
                ServiceCost(service="Fixture refund", amount=Decimal("-1.23"), currency="USD")
            ],
            totals=[CurrencyCost(amount=Decimal("-1.23"), currency="USD")],
            limitations=["Disposable SDK fixture only; no AWS call"],
        )

    assert run_once(org, runner) and not run_once(org, runner) and len(calls) == 1
    with factory() as db:
        report = read_report(db, principal, UUID(key))
        assert report.totals[0].amount == Decimal("-1.23")
        raw = db.get(BillingCollection, key).report
        raw = {**raw, "organization_id": identifier()}
        # Terminal evidence cannot be changed, even with an otherwise valid JSON envelope.
        with pytest.raises(DBAPIError):
            db.execute(
                update(BillingCollection).where(BillingCollection.id == key).values(report=raw)
            )
        db.rollback()
