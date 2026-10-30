"""Run only with migration credentials. Runtime gets no schema or role ownership."""

import os

from app import models  # noqa: F401 - register the explicit application table allowlist
from app.core.db import Base, engine
from psycopg import sql

password = os.environ["MESH_DB_PASSWORD"]
if len(password) < 24:
    raise ValueError("Use a randomly generated runtime password of at least 24 characters")
with engine.begin() as connection:
    driver = connection.connection.driver_connection
    with driver.cursor() as cursor:
        cursor.execute("SELECT rolsuper,rolbypassrls FROM pg_roles WHERE rolname = 'mesh_runtime'")
        existing = cursor.fetchone()
        if existing is None:
            cursor.execute(
                sql.SQL(
                    "CREATE ROLE mesh_runtime LOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE NOINHERIT PASSWORD {}"
                ).format(sql.Literal(password))
            )
        else:
            if any(existing):
                raise RuntimeError(
                    "Existing runtime role has unsafe flags; an administrator must remove them"
                )
            # Managed PostgreSQL administrators cannot ALTER SUPERUSER/BYPASSRLS
            # attributes even to false. Verify them, then alter only owned flags.
            cursor.execute(
                sql.SQL(
                    "ALTER ROLE mesh_runtime NOCREATEDB NOCREATEROLE NOINHERIT PASSWORD {}"
                ).format(sql.Literal(password))
            )
        cursor.execute(
            "SELECT parent.rolname FROM pg_auth_members membership JOIN pg_roles parent ON parent.oid=membership.roleid JOIN pg_roles member ON member.oid=membership.member WHERE member.rolname='mesh_runtime'"
        )
        for (parent,) in cursor.fetchall():
            cursor.execute(sql.SQL("REVOKE {} FROM mesh_runtime").format(sql.Identifier(parent)))
        cursor.execute("GRANT USAGE ON SCHEMA public TO mesh_runtime")
        for table in Base.metadata.tables:
            cursor.execute(
                sql.SQL("GRANT SELECT, INSERT, UPDATE ON TABLE public.{} TO mesh_runtime").format(
                    sql.Identifier(table)
                )
            )
        cursor.execute("REVOKE ALL ON alembic_version FROM mesh_runtime")
        cursor.execute(
            "REVOKE UPDATE ON audit_logs, trust_events, audit_seals, payroll_rules, payroll_calculations, job_roles, employment_terms, incident_notes, webhook_deliveries, cloud_assessments, project_approval_policies, project_reviews, risk_policies, risk_assessments, security_events, anomalies, finding_identities, correlation_policies, ai_usage, ai_request_events FROM mesh_runtime"
        )
        cursor.execute("REVOKE CREATE ON SCHEMA public FROM mesh_runtime")
        cursor.execute(
            "SELECT to_regprocedure('public.mesh_retire_telemetry(integer,integer)') IS NOT NULL"
        )
        if cursor.fetchone()[0]:
            cursor.execute(
                "GRANT EXECUTE ON FUNCTION public.mesh_retire_telemetry(integer,integer) TO mesh_runtime"
            )
        cursor.execute(
            "SELECT to_regprocedure('public.mesh_rehire_clear_project_grants(text)') IS NOT NULL"
        )
        if cursor.fetchone()[0]:
            cursor.execute(
                "GRANT EXECUTE ON FUNCTION public.mesh_rehire_clear_project_grants(text) TO mesh_runtime"
            )
        for function in (
            "public.mesh_retire_telemetry(integer,integer)",
            "public.mesh_rehire_clear_project_grants(text)",
        ):
            cursor.execute("SELECT to_regprocedure(%s) IS NOT NULL", (function,))
            if cursor.fetchone()[0]:
                cursor.execute("REVOKE ALL ON FUNCTION " + function + " FROM PUBLIC")
                for api_role in ("anon", "authenticated", "service_role"):
                    cursor.execute("SELECT 1 FROM pg_roles WHERE rolname=%s", (api_role,))
                    if cursor.fetchone():
                        cursor.execute(
                            sql.SQL("REVOKE ALL ON FUNCTION " + function + " FROM {}").format(
                                sql.Identifier(api_role)
                            )
                        )
        cursor.execute("SELECT has_schema_privilege('mesh_runtime', 'public', 'CREATE')")
        if cursor.fetchone()[0]:
            raise RuntimeError(
                "Runtime inherits public schema CREATE; review database schema grants before setup"
            )
