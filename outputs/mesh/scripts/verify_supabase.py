"""Live, rollback-only database verification. Never creates Auth users or sends mail.

Run from the backend root with its local .env configured. Synthetic organization
and employee rows are rolled back, including audit rows; no cleanup DELETE needed.
"""

import json
import os
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import psycopg
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from dotenv import dotenv_values, load_dotenv
from psycopg import sql
from sqlalchemy import create_engine, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
sys.path.insert(0, str(ROOT / "backend"))

from app.auth import Principal  # noqa: E402
from app.core.db import Base, assert_runtime_role, tenant_context  # noqa: E402
from app.models import Employee, IdentitySession, Membership, Organization, identifier, now  # noqa: E402
from app.services import audit, verify_audit  # noqa: E402


def verify() -> dict:
    setup_path = Path(
        os.getenv("MESH_SUPABASE_SETUP_FILE", str(ROOT.parents[1] / "work/supabase-setup.env"))
    )
    config = {**dotenv_values(ROOT / ".env"), **dotenv_values(setup_path)}
    checks = {}
    reference = config["SUPABASE_PROJECT_REF"]
    with psycopg.connect(
        host=config["SUPABASE_DB_HOST"],
        port=5432,
        user="postgres." + reference,
        dbname="postgres",
        password=config["SUPABASE_DB_PASSWORD"],
        sslmode="verify-full",
        sslrootcert=str(ROOT / "supabase/supabase-ca.crt"),
        connect_timeout=15,
        options="-c statement_timeout=15000 -c lock_timeout=5000",
    ) as admin:
        with admin.cursor() as cursor:
            cursor.execute("SELECT version_num FROM public.alembic_version")
            alembic = Config(str(ROOT / "alembic.ini"))
            alembic.set_main_option("script_location", str(ROOT / "backend/migrations"))
            expected_revision = ScriptDirectory.from_config(alembic).get_current_head()
            assert cursor.fetchone()[0] == expected_revision
            checks["migration_revision_" + expected_revision] = "passed"
            for function in (
                "public.mesh_retire_telemetry(integer,integer)",
                "public.mesh_rehire_clear_project_grants(text)",
            ):
                cursor.execute(
                    "SELECT has_function_privilege('mesh_runtime',%s,'EXECUTE')", (function,)
                )
                assert cursor.fetchone()[0]
                cursor.execute(
                    "SELECT rolname,has_function_privilege(rolname,%s,'EXECUTE') FROM pg_roles WHERE rolname IN ('anon','authenticated','service_role')",
                    (function,),
                )
                assert not any(value for _, value in cursor.fetchall())
            checks["backend_only_function_api_grants_denied_runtime_preserved"] = "passed"

            cursor.execute(
                "SELECT relname,relrowsecurity,relforcerowsecurity FROM pg_class "
                "WHERE relnamespace='public'::regnamespace AND relkind='r'"
            )
            tables = {name: (enabled, forced) for name, enabled, forced in cursor.fetchall()}
            assert set(Base.metadata.tables) <= tables.keys()
            assert all(tables[name] == (True, True) for name in Base.metadata.tables)
            checks[f"all_{len(Base.metadata.tables)}_tables_enable_and_force_rls"] = "passed"
            cursor.execute(
                "SELECT tablename FROM pg_policies WHERE schemaname='public' "
                "AND policyname='tenant_boundary' AND tablename=ANY(%s)",
                (list(Base.metadata.tables),),
            )
            assert {row[0] for row in cursor.fetchall()} == set(Base.metadata.tables)
            cursor.execute(
                "SELECT tbl,role_name,priv FROM unnest(%s::text[]) AS tbl "
                "CROSS JOIN unnest(ARRAY['anon','authenticated']) AS role_name "
                "CROSS JOIN unnest(ARRAY['SELECT','INSERT','UPDATE','DELETE','TRUNCATE']) AS priv "
                "WHERE has_table_privilege(role_name,'public.' || tbl,priv)",
                ([*Base.metadata.tables, "alembic_version"],),
            )
            assert cursor.fetchall() == []
            checks["all_tenant_policies_and_browser_table_grants"] = "passed"
            cursor.execute(
                "SELECT has_table_privilege('mesh_runtime','public.finding_identities','SELECT'),has_table_privilege('mesh_runtime','public.finding_identities','INSERT'),has_table_privilege('mesh_runtime','public.finding_identities','UPDATE'),has_table_privilege('mesh_runtime','public.finding_identities','DELETE')"
            )
            assert cursor.fetchone() == (True, True, False, False)
            checks["finding_identity_runtime_append_only_grants"] = "passed"
            cursor.execute(
                "SELECT has_table_privilege('mesh_runtime','public.correlation_policies','SELECT'),has_table_privilege('mesh_runtime','public.correlation_policies','INSERT'),has_table_privilege('mesh_runtime','public.correlation_policies','UPDATE'),has_table_privilege('mesh_runtime','public.correlation_policies','DELETE')"
            )
            assert cursor.fetchone() == (True, True, False, False)
            checks["correlation_policy_runtime_append_only_grants"] = "passed"
            cursor.execute(
                "SELECT public,file_size_limit,allowed_mime_types FROM storage.buckets "
                "WHERE id='mesh-identity'"
            )
            public, limit, types = cursor.fetchone()
            assert public is False and limit == 2097152
            assert set(types) == {"image/png", "image/jpeg"}
            checks["private_bucket_size_and_mime_limits"] = "passed"
            cursor.execute(
                "SELECT policyname,permissive,roles,cmd FROM pg_policies "
                "WHERE schemaname='storage' AND tablename='objects' "
                "AND policyname LIKE 'mesh_identity_no_client_%'"
            )
            policies = cursor.fetchall()
            assert len(policies) == 4
            assert {row[3] for row in policies} == {"SELECT", "INSERT", "UPDATE", "DELETE"}
            assert all(
                row[1] == "RESTRICTIVE" and set(row[2]) == {"anon", "authenticated"}
                for row in policies
            )
            checks["four_restrictive_storage_policies"] = "passed"
            # The script is intentionally reapplicable; validate without persisting DDL.
            with admin.transaction(force_rollback=True):
                cursor.execute((ROOT / "supabase/storage/0001_private_identity.sql").read_text())
            checks["storage_policy_reapplication"] = "passed"
            # Validate each browser role under database-enforced permissions.
            for role in ("anon", "authenticated"):
                try:
                    with admin.transaction():
                        cursor.execute(sql.SQL("SET LOCAL ROLE {}").format(sql.Identifier(role)))
                        cursor.execute("SELECT * FROM public.employees LIMIT 1")
                except psycopg.errors.InsufficientPrivilege:
                    pass
                else:
                    raise AssertionError("Direct browser table access was accepted")
            checks["browser_roles_reject_direct_employee_queries"] = "passed"
            with admin.transaction(force_rollback=True):
                org, audit_id, actor = identifier(), identifier(), identifier()
                cursor.execute(
                    "INSERT INTO organizations(id,name,status,verification_status,created_at) "
                    "VALUES (%s,'Rollback verification','active','unverified',now())",
                    (org,),
                )
                cursor.execute(
                    "INSERT INTO audit_logs(id,organization_id,actor_id,action,target_id,outcome,created_at) "
                    "VALUES (%s,%s,%s,'fixture',%s,'success',now())",
                    (audit_id, org, actor, org),
                )
                try:
                    with admin.transaction():
                        cursor.execute(
                            "UPDATE audit_logs SET action='tampered' WHERE id=%s", (audit_id,)
                        )
                except psycopg.errors.RaiseException as exc:
                    assert exc.sqlstate == "P0001"
                else:
                    raise AssertionError("Audit append-only trigger did not reject mutation")
            checks["audit_trigger_rejects_administrator_update"] = "passed"

    engine = create_engine(os.environ["DATABASE_URL"], pool_pre_ping=True)
    org_a, org_b, user = identifier(), identifier(), identifier()
    try:
        with engine.connect() as connection:
            differences = compare_metadata(
                MigrationContext.configure(connection, opts={"compare_type": True}), Base.metadata
            )
            assert differences == []
            checks["hosted_schema_matches_application_metadata"] = "passed"
        with Session(engine) as db:
            assert_runtime_role(db)
            assert db.scalar(text("SELECT current_user")) == "mesh_runtime"
            checks["restricted_runtime_login_and_role_safety"] = "passed"
            for org in (org_a, org_b):
                tenant_context(db, org, user)
                db.add(Organization(id=org, name="Rollback-only MESH verification"))
                db.flush()
                db.add(
                    Membership(
                        organization_id=org,
                        user_id=user,
                        email=user + "@example.invalid",
                        role="junior_developer",
                    )
                )
                db.flush()
                db.add(
                    Employee(
                        organization_id=org,
                        user_id=user,
                        name="Synthetic fixture",
                        department="Verification",
                    )
                )
                db.flush()
            tenant_context(db, org_a, user)
            rows = db.scalars(select(Employee)).all()
            assert len(rows) == 1 and rows[0].organization_id == org_a
            assert db.scalars(select(Employee).where(Employee.organization_id == org_b)).all() == []
            checks["unscoped_select_and_cross_tenant_read_isolation"] = "passed"
            with db.begin_nested():
                try:
                    with db.begin_nested():
                        db.execute(
                            text("SELECT public.mesh_rehire_clear_project_grants(:plan)"),
                            {"plan": identifier()},
                        )
                except DBAPIError as error:
                    assert error.orig.sqlstate == "42501"
                else:
                    raise AssertionError("Unprivileged runtime caller could clear project grants")
            checks["rehire_function_rejects_unprivileged_runtime_caller"] = "passed"

            try:
                with db.begin_nested():
                    db.add(
                        Employee(
                            organization_id=org_b,
                            user_id=identifier(),
                            name="Forbidden fixture",
                            department="Verification",
                        )
                    )
                    db.flush()
            except DBAPIError as exc:
                assert exc.orig.sqlstate == "42501"
            else:
                raise AssertionError("Cross-tenant write was accepted")
            checks["cross_tenant_write_rejection"] = "passed"
            session_a = IdentitySession(
                user_id=user,
                provider_session_id=identifier(),
                client_hint="Fixture",
                ip_digest="0" * 64,
                expires_at=now() + timedelta(hours=1),
            )
            db.add(session_a)
            db.flush()
            other_user = identifier()
            tenant_context(db, org_a, other_user)
            db.add(
                IdentitySession(
                    user_id=other_user,
                    provider_session_id=identifier(),
                    client_hint="Fixture",
                    ip_digest="0" * 64,
                    expires_at=now() + timedelta(hours=1),
                )
            )
            db.flush()
            observed = db.scalars(select(IdentitySession)).all()
            assert len(observed) == 1 and observed[0].user_id == other_user
            try:
                with db.begin_nested():
                    db.add(
                        IdentitySession(
                            user_id=user,
                            provider_session_id=identifier(),
                            client_hint="Forbidden",
                            ip_digest="0" * 64,
                            expires_at=now() + timedelta(hours=1),
                        )
                    )
                    db.flush()
            except DBAPIError as exc:
                assert exc.orig.sqlstate == "42501"
            else:
                raise AssertionError("Self-owned session policy accepted another user's record")
            checks["self_owned_session_rls_rejects_other_user_reads_and_writes"] = "passed"
            tenant_context(db, org_a, user)
            principal = Principal(user, org_a, "junior_developer")
            audit(db, principal, "verification.fixture", org_a)
            result = verify_audit(db, principal)
            assert result["valid"] is True
            checks["audit_append_and_hash_verification"] = "passed"
            try:
                with db.begin_nested():
                    db.execute(text("UPDATE audit_logs SET action='tampered'"))
            except DBAPIError as exc:
                assert exc.orig.sqlstate == "42501"
            else:
                raise AssertionError("Runtime audit mutation was accepted")
            checks["runtime_audit_update_denied"] = "passed"
            db.rollback()
            assert (
                db.scalar(text("SELECT nullif(current_setting('mesh.organization_id',true),'')"))
                is None
            )
            assert db.scalars(select(Employee)).all() == []
            checks["transaction_context_reset"] = "passed"
            tenant_context(db, org_a, user)
            assert db.scalar(select(Organization).where(Organization.id == org_a)) is None
            checks["synthetic_fixtures_rolled_back"] = "passed"
    finally:
        engine.dispose()

    with httpx.Client(timeout=15, follow_redirects=False) as client:
        url = config["SUPABASE_URL"].rstrip("/")
        headers = {"apikey": config["SUPABASE_ANON_KEY"]}
        response = client.get(url + "/auth/v1/.well-known/jwks.json", headers=headers)
        response.raise_for_status()
        assert any(key.get("alg") in {"ES256", "RS256"} for key in response.json()["keys"])
        checks["live_asymmetric_jwks"] = "passed"
        response = client.get(url + "/auth/v1/settings", headers=headers)
        response.raise_for_status()
        assert response.json()["external"]["email"] is True
        assert response.json()["mailer_autoconfirm"] is False
        checks["live_email_auth_and_confirmation_settings"] = "passed"
        response = client.get(url + "/rest/v1/employees?select=id&limit=1", headers=headers)
        assert response.status_code in {401, 403}
        checks["live_postgrest_browser_access_denied"] = "passed"
    return {
        "project_ref": reference,
        "verified_at_utc": datetime.now(UTC).isoformat(),
        "checks": checks,
        "limitations": [
            "This schema verifier does not exercise Auth provider journeys; see separate supabase-provider-results.json evidence.",
            "Storage upload/sign/download and client denial evidence is recorded separately in supabase-provider-results.json.",
            "ClamAV, SMTP and Redis are not running locally.",
            "Concurrent rollback-only audit append evidence is recorded separately in supabase-concurrency-results.json.",
        ],
    }


if __name__ == "__main__":
    try:
        report = verify()
    except Exception as exc:
        # Driver/HTTP exception text can embed secrets; report only safe classifications.
        print(
            json.dumps({"failed": type(exc).__name__, "sqlstate": getattr(exc, "sqlstate", None)})
        )
        raise SystemExit(1) from None
    (ROOT / "docs/supabase-live-results.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
