"""Opt-in portable PostgreSQL acceptance; creates only a new disposable local cluster.

Never reads hosted .env or installs a Windows service. Requires trusted PostgreSQL
binaries and an explicit workspace directory for generated synthetic fixtures.
"""

import argparse
import json
import os
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

import psycopg
from dotenv import dotenv_values
from psycopg import sql
from sqlalchemy import URL
from verify_docker_runtime import disposable_environment, migration_head

ROOT = Path(__file__).resolve().parents[1]


@contextmanager
def synthetic_workspace(workspace: Path):
    work = Path(tempfile.mkdtemp(prefix="mesh-native-pg-", dir=workspace))
    try:
        yield work
    except BaseException:
        # Preserve the cluster if stopping its server failed.
        raise
    else:
        assert work.resolve().is_relative_to(workspace.resolve())
        assert work.name.startswith("mesh-native-pg-") and not work.is_symlink()
        shutil.rmtree(work)


def verify(binaries: Path, workspace: Path, dedicated: bool) -> dict:
    if not dedicated or not binaries.is_absolute() or not workspace.is_absolute():
        raise ValueError("Absolute tool/workspace paths and explicit disposable opt-in required")
    if not workspace.is_dir() or workspace.is_symlink():
        raise ValueError("Existing ordinary workspace directory required")
    suffix = ".exe" if os.name == "nt" else ""
    tools = {
        name: binaries / (name + suffix)
        for name in ("postgres", "initdb", "pg_ctl", "pg_dump", "pg_restore")
    }
    if not all(path.is_file() for path in tools.values()):
        raise ValueError("Trusted PostgreSQL runtime is incomplete")
    checks = {}
    with synthetic_workspace(workspace) as work:
        assert work.resolve().is_relative_to(workspace.resolve())
        cluster = work / "cluster"
        password = secrets.token_urlsafe(32)
        password_file = work / "init-password"
        password_file.write_text(password + "\n")
        database = "mesh_test_" + uuid4().hex
        restored = "mesh_test_restore_" + uuid4().hex
        fixture = str(uuid4())
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            port = listener.getsockname()[1]
        environment = {
            **disposable_environment(dict(dotenv_values(ROOT / ".env.example"))),
            "PGHOST": "127.0.0.1",
            "PGPORT": str(port),
            "PGUSER": "mesh_admin",
            "PGPASSWORD": password,
        }
        started = False

        def run(command, label, timeout=90, env=None, cwd=ROOT):
            with (work / (label + ".log")).open("wb") as log:
                result = subprocess.run(
                    command,
                    cwd=cwd,
                    env=environment if env is None else env,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    timeout=timeout,
                    check=False,
                )
            if result.returncode:
                raise RuntimeError(label + " failed")

        def connect(name="postgres"):
            return psycopg.connect(
                host="127.0.0.1",
                port=port,
                user="mesh_admin",
                password=password,
                dbname=name,
                autocommit=True,
                connect_timeout=5,
            )

        try:
            run(
                [
                    str(tools["initdb"]),
                    "-D",
                    str(cluster),
                    "-U",
                    "mesh_admin",
                    "--pwfile",
                    str(password_file),
                    "--auth=scram-sha-256",
                    "--encoding=UTF8",
                    "--locale=C",
                ],
                "initialize",
            )
            password_file.unlink()
            started = True  # stop is attempted even after partial startup.
            run(
                [
                    str(tools["pg_ctl"]),
                    "-D",
                    str(cluster),
                    "-l",
                    str(work / "server.log"),
                    "-o",
                    f"-h 127.0.0.1 -p {port} -c max_connections=30 -c shared_buffers=32MB",
                    "-w",
                    "-t",
                    "30",
                    "start",
                ],
                "start",
            )
            with connect() as admin:
                assert admin.execute("SHOW listen_addresses").fetchone()[0] == "127.0.0.1"
                admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database)))
            checks["actual_loopback_only_scram_postgresql_start"] = "passed"
            url = URL.create(
                "postgresql+psycopg",
                username="mesh_admin",
                password=password,
                host="127.0.0.1",
                port=port,
                database=database,
            ).render_as_string(hide_password=False)
            test_environment = {**environment, "MESH_POSTGRES_ADMIN_URL": url}
            context = work / "context"
            context.mkdir()
            for source in (ROOT / "backend").rglob("*.py"):
                if source.is_symlink():
                    raise ValueError("Test context must not contain source symlinks")
                target = context / "backend" / source.relative_to(ROOT / "backend")
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, target)
            for name in ("pyproject.toml", "alembic.ini"):
                shutil.copyfile(ROOT / name, context / name)
            assert not (context / ".env").exists()
            run(
                [
                    sys.executable,
                    "-m",
                    "pytest",
                    "-q",
                    "-p",
                    "no:cacheprovider",
                    "backend/tests/test_postgres_integration.py",
                    "--junitxml=" + str(ROOT / "docs/postgres-native-test-results.xml"),
                ],
                "integration",
                180,
                test_environment,
                cwd=context,
            )
            suites = list(
                ET.parse(ROOT / "docs/postgres-native-test-results.xml").getroot().iter("testsuite")
            )
            integration_cases = sum(int(suite.get("tests", 0)) for suite in suites)
            assert integration_cases > 0 and not any(
                int(suite.get(key, 0))
                for suite in suites
                for key in ("failures", "errors", "skipped")
            ), "Native PostgreSQL acceptance must execute every collected case"
            checks[
                "actual_disposable_postgresql_rls_audit_risk_lifecycle_scan_concurrency_cases"
            ] = "passed"
            with connect(database) as db:
                db.execute(
                    "INSERT INTO organizations(id,name,status,verification_status,created_at) VALUES (%s,%s,'active','unverified',now())",
                    (fixture, "Disposable backup fixture"),
                )
            dump = work / "fixture.dump"
            run([str(tools["pg_dump"]), "-Fc", "-d", database, "-f", str(dump)], "dump")
            with connect() as admin:
                admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(restored)))
            run([str(tools["pg_restore"]), "--exit-on-error", "-d", restored, str(dump)], "restore")

            def snapshot(name):
                with connect(name) as db:
                    return {
                        "revision": db.execute(
                            "SELECT version_num FROM alembic_version"
                        ).fetchone()[0],
                        "tables": db.execute(
                            "SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' AND c.relkind='r'"
                        ).fetchone()[0],
                        "rls": db.execute(
                            "SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' AND c.relkind='r' AND c.relrowsecurity AND c.relforcerowsecurity"
                        ).fetchone()[0],
                        "policies": db.execute(
                            "SELECT count(*) FROM pg_policies WHERE schemaname='public'"
                        ).fetchone()[0],
                        "fixture": db.execute(
                            "SELECT count(*) FROM organizations WHERE id=%s", (fixture,)
                        ).fetchone()[0],
                    }

            before, after = snapshot(database), snapshot(restored)
            assert before == after
            assert after["revision"] == migration_head() and after["rls"] == 57
            assert after["policies"] >= 57 and after["fixture"] == 1
            checks["actual_dump_restore_schema_rls_policies_and_fixture_equivalence"] = "passed"
            frozen_database = "mesh_test_frozen_" + uuid4().hex
            with connect() as admin:
                for role in ("anon", "authenticated", "service_role"):
                    admin.execute(
                        sql.SQL("CREATE ROLE {} NOLOGIN NOSUPERUSER NOBYPASSRLS").format(
                            sql.Identifier(role)
                        )
                    )
                admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(frozen_database)))
            paths = sorted((ROOT / "supabase/migrations").glob("*.sql"))
            assert paths[0].name == "20261023000100_mesh_fresh_project.sql"
            with connect(frozen_database) as db:
                # Execute the complete artifacts, including Storage DDL, against
                # a minimal catalog fixture. Real provider/API checks are separate.
                db.execute(
                    "CREATE SCHEMA storage; CREATE TABLE storage.buckets(id text PRIMARY KEY,name text,public boolean,file_size_limit bigint,allowed_mime_types text[]); CREATE TABLE storage.objects(id text PRIMARY KEY,bucket_id text REFERENCES storage.buckets(id)); ALTER TABLE storage.objects ENABLE ROW LEVEL SECURITY"
                )
                db.execute(
                    "ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT EXECUTE ON FUNCTIONS TO anon,authenticated,service_role"
                )
                for path in paths:
                    if path.name == "20261026000200_ai_accounting.sql":
                        db.execute(
                            "ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO anon,authenticated,service_role"
                        )
                    db.execute(path.read_text(encoding="utf-8-sig"), prepare=False)
                assert (
                    db.execute("SELECT version_num FROM public.alembic_version").fetchone()[0]
                    == migration_head()
                )
                assert (
                    db.execute(
                        "SELECT count(*) FROM pg_class WHERE relnamespace='public'::regnamespace AND relkind='r' AND relrowsecurity AND relforcerowsecurity"
                    ).fetchone()[0]
                    == 57
                )
                assert (
                    db.execute(
                        "SELECT count(*) FROM pg_trigger WHERE tgname='immutable_observation' AND tgrelid IN ('public.security_events'::regclass,'public.anomalies'::regclass)"
                    ).fetchone()[0]
                    == 2
                )
                assert (
                    db.execute(
                        "SELECT count(*) FROM pg_policies WHERE schemaname='storage' AND tablename='objects' AND policyname LIKE 'mesh_identity_no_client_%' AND permissive='RESTRICTIVE'"
                    ).fetchone()[0]
                    == 4
                )
                for function in (
                    "public.mesh_retire_telemetry(integer,integer)",
                    "public.mesh_rehire_clear_project_grants(text)",
                    "public.mesh_guard_ai_request()",
                    "public.mesh_guard_billing_collection()",
                ):
                    assert not any(
                        value
                        for _, value in db.execute(
                            "SELECT rolname,has_function_privilege(rolname,%s,'EXECUTE') FROM pg_roles WHERE rolname IN ('anon','authenticated','service_role')",
                            (function,),
                        )
                    )
                for table in ("public.ai_requests", "public.ai_request_events"):
                    assert not any(
                        value
                        for _, value in db.execute(
                            "SELECT rolname,has_table_privilege(rolname,%s,'SELECT,INSERT,UPDATE,DELETE') FROM pg_roles WHERE rolname IN ('anon','authenticated','service_role')",
                            (table,),
                        )
                    )
                db.execute(
                    "INSERT INTO storage.buckets(id,name,public) VALUES ('fixture-public','fixture-public',true); INSERT INTO storage.objects(id,bucket_id) VALUES ('private','mesh-identity'),('public','fixture-public'); GRANT USAGE ON SCHEMA storage TO anon,authenticated; GRANT SELECT ON storage.objects TO anon,authenticated; CREATE POLICY fixture_permissive_read ON storage.objects FOR SELECT TO anon,authenticated USING(true)"
                )
                for role in ("anon", "authenticated"):
                    with db.transaction():
                        db.execute(sql.SQL("SET LOCAL ROLE {}").format(sql.Identifier(role)))
                        assert db.execute(
                            "SELECT id FROM storage.objects ORDER BY id"
                        ).fetchall() == [("public",)]
            (ROOT / "docs/supabase-frozen-sql-local-results.json").write_text(
                json.dumps(
                    {
                        "passed": True,
                        "revision": migration_head(),
                        "migration_files": len(paths),
                        "entire_artifacts_applied_in_lexicographic_cli_order": True,
                        "forced_rls_tables": 57,
                        "supabase_style_default_function_grants_explicitly_removed": True,
                        "four_restrictive_storage_policies_override_permissive_fixture_read": True,
                        "limitations": [
                            "Actual fresh PostgreSQL execution, with a minimal Supabase-shaped Storage catalog fixture.",
                            "Not an actual local Supabase Storage/Auth service or CLI history repair. Hosted provider/policy acceptance is separate.",
                            "Generated database/roles are removed with the disposable native cluster.",
                        ],
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            checks["actual_fresh_frozen_sql_order_and_storage_catalog_policy_fixture"] = "passed"
        except Exception as error:
            checks["acceptance"] = "failed: " + type(error).__name__
            # Logs stay outside deliverables and can contain generated fixture credentials.
            failure = workspace / "native-postgres-last-failure.log"
            with failure.open("wb") as output:
                for path in sorted(work.glob("*.log")):
                    output.write((path.name + "\n").encode())
                    output.write(path.read_bytes())
        finally:
            if started:
                try:
                    run(
                        [
                            str(tools["pg_ctl"]),
                            "-D",
                            str(cluster),
                            "-m",
                            "fast",
                            "-w",
                            "-t",
                            "30",
                            "stop",
                        ],
                        "stop",
                        45,
                    )
                    checks["disposable_postgresql_stopped"] = "passed"
                except Exception as error:
                    checks["disposable_postgresql_stopped"] = "failed: " + type(error).__name__
                    raise RuntimeError(
                        "Stop disposable PostgreSQL before removing its cluster"
                    ) from None
    checks["synthetic_cluster_and_backup_removed"] = "passed"
    return {
        "checks": checks,
        "postgresql_integration_cases": integration_cases,
        "passed": all(value == "passed" for value in checks.values()),
        "limitations": [
            "Native local PostgreSQL 16 acceptance; does not establish Docker Compose or Linux runtime acceptance.",
            "Only a generated local cluster and synthetic data; hosted credentials and data are not used.",
        ],
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--postgres-bin", type=Path, required=True)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--disposable-local-cluster", action="store_true")
    args = parser.parse_args()
    report = verify(args.postgres_bin, args.workspace, args.disposable_local_cluster)
    (ROOT / "docs/postgres-native-results.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    raise SystemExit(0 if report["passed"] else 1)
