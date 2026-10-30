"""Opt-in isolated Compose and Linux/PostgreSQL acceptance on a dedicated Docker host.

Never reads hosted .env. Generates its own project, passwords, tenant and volumes.
Only that generated Compose project's resources are removed on completion.
"""

import argparse
import hashlib
import importlib.metadata
import json
import os
import re
import secrets
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from uuid import uuid4

from alembic.script import ScriptDirectory
from cryptography.fernet import Fernet
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]


def owned_image_tags(project: str, tags: list[str]) -> list[str]:
    if not re.fullmatch(r"mesh-test-[a-f0-9]{12}", project):
        raise ValueError("Generated acceptance project required")
    allowed = {
        f"{project}-{service}:{tag}"
        for service in (
            "api",
            "worker",
            "cloud-worker",
            "billing-worker",
            "migrate",
            "retention",
            "backend",
            "tests",
        )
        for tag in ("latest", "acceptance")
    }
    return sorted(allowed & set(tags))


def required_wheel(filename: str, versions: dict[str, str]) -> bool:
    parts = filename.split("-", 2)
    if Path(filename).name != filename or not filename.endswith(".whl") or len(parts) != 3:
        raise ValueError("Invalid wheel manifest path")
    name = parts[0].lower().replace("_", "-")
    return versions.get(name) == parts[1]


def migration_head() -> str:
    head = ScriptDirectory(str(ROOT / "backend/migrations")).get_current_head()
    if head is None:
        raise RuntimeError("Migration head is missing")
    return head


def disposable_environment(config: dict, inherited: dict | None = None) -> dict:
    environment = dict(os.environ if inherited is None else inherited)
    for key in config:
        environment.pop(key, None)
    for key in list(environment):
        if key.startswith("COMPOSE_"):
            environment.pop(key)
    return {**environment, "DOCKER_BUILDKIT": "0", "COMPOSE_PARALLEL_LIMIT": "1"}


def verify(
    docker: Path,
    compose: Path,
    dedicated: bool,
    offline_wheels: Path | None = None,
    prebuilt_image: str | None = None,
):
    if not dedicated:
        raise ValueError("Explicit dedicated Docker host opt-in required")
    if prebuilt_image is not None and not re.fullmatch(
        r"[A-Za-z0-9][A-Za-z0-9_./:@-]{0,254}", prebuilt_image
    ):
        raise ValueError("Invalid prebuilt image reference")
    assert all(path.is_absolute() and path.is_file() for path in [docker, compose])
    project = "mesh-test-" + uuid4().hex[:12]
    assert re.fullmatch(r"mesh-test-[a-f0-9]{12}", project)
    tenant = str(uuid4())
    checks = {}
    runtime_image_id = None
    app_source_fingerprint = hashlib.sha256(
        b"".join(
            path.relative_to(ROOT).as_posix().encode()
            + b"\0"
            + hashlib.sha256(path.read_bytes()).digest()
            for path in sorted((ROOT / "backend/app").rglob("*.py"))
        )
    ).hexdigest()
    environment = {**os.environ, "DOCKER_BUILDKIT": "0", "COMPOSE_PARALLEL_LIMIT": "1"}
    workspace = ROOT.parents[1] / "work"
    workspace.mkdir(exist_ok=True)
    ledger = workspace / "docker-runtime-fixtures.json"
    assert not ledger.exists(), "An unresolved disposable Compose project requires cleanup first"
    with tempfile.TemporaryDirectory(prefix="mesh-compose-acceptance-", dir=workspace) as folder:
        work = Path(folder)
        assert work.resolve().is_relative_to(workspace.resolve())
        context = work / "context"
        context.mkdir()
        excluded = {"__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".venv", ".git"}
        for directory, folders, filenames in os.walk(ROOT):
            folders[:] = [
                name for name in folders if name not in excluded and not name.endswith(".egg-info")
            ]
            target = context / Path(directory).relative_to(ROOT)
            target.mkdir(parents=True, exist_ok=True)
            for name in filenames:
                if name.startswith(".env") and name != ".env.example":
                    continue
                source = Path(directory) / name
                assert not source.is_symlink(), "Build context must not contain source symlinks"
                shutil.copyfile(source, target / name)
        if offline_wheels is not None:
            if not offline_wheels.is_absolute() or not offline_wheels.is_dir():
                raise ValueError("Offline wheel cache must be an absolute directory")
            manifest = json.loads((offline_wheels / "manifest.json").read_text())
            wheel_target = context / ".runtime-wheelhouse"
            wheel_target.mkdir()
            # Scanner wheels may share this cache but are not API/test dependencies.
            # Excluding them avoids embedding the large Semgrep binary in the API image.
            required = {
                line.split("==", 1)[0].lower().replace("_", "-")
                for line in (ROOT / "requirements.lock").read_text().splitlines()
                if "==" in line and not line.startswith("#")
            } | {
                "pytest",
                "pluggy",
                "iniconfig",
                "packaging",
                "pygments",
                "bandit",
                "pyyaml",
                "rich",
                "stevedore",
                "markdown-it-py",
                "mdurl",
                "setuptools",
                "wheel",
            }
            versions = {}
            for lock_name in (
                "requirements-dev.lock",
                "requirements.lock",
                "requirements-build.lock",
            ):
                for line in (ROOT / lock_name).read_text().splitlines():
                    if "==" in line and not line.startswith("#"):
                        name, version = line.split()[0].split("==", 1)
                        normalized = name.lower().replace("_", "-")
                        if normalized in required:
                            versions[normalized] = version
            if required != set(versions):
                raise ValueError("Exact offline dependency versions are missing")
            for record in manifest["files"]:
                name = record["file"]
                if Path(name).name != name or not name.endswith(".whl"):
                    raise ValueError("Invalid wheel manifest path")
                if not required_wheel(name, versions):
                    continue
                source = offline_wheels / name
                if (
                    source.is_symlink()
                    or hashlib.sha256(source.read_bytes()).hexdigest() != record["sha256"]
                ):
                    raise ValueError("Offline wheel hash mismatch")
                shutil.copyfile(source, wheel_target / name)
            dockerfile = context / "infrastructure/docker/Dockerfile"
            text = dockerfile.read_text()
            old = "RUN pip install --no-cache-dir --require-hashes -r requirements-hashed.lock"
            build_install = (
                "RUN pip install --no-cache-dir --require-hashes -r requirements-build.lock"
            )
            if old not in text or build_install not in text:
                raise ValueError("Unexpected runtime Dockerfile installation command")
            new = "COPY .runtime-wheelhouse /opt/mesh/wheels\nRUN pip install --no-cache-dir --no-index --find-links=/opt/mesh/wheels --require-hashes -r requirements-hashed.lock"
            dockerfile.write_text(
                text.replace(old, new).replace(
                    build_install,
                    "COPY .runtime-wheelhouse /opt/mesh/wheels\nRUN pip install --no-cache-dir --no-index --find-links=/opt/mesh/wheels --require-hashes -r requirements-build.lock",
                ),
                encoding="utf-8",
            )
        config = {k: v for k, v in dotenv_values(ROOT / ".env.example").items() if v is not None}
        config.update(
            {
                "POSTGRES_ADMIN_PASSWORD": secrets.token_urlsafe(32),
                "MESH_DB_PASSWORD": secrets.token_urlsafe(32),
                "AUTH_RATE_SECRET": secrets.token_urlsafe(48),
                "MAIL_ENCRYPTION_KEY": Fernet.generate_key().decode(),
                "WORKER_ORGANIZATION_ID": tenant,
                "SMTP_HOST": "mailpit",
                "REQUIRE_PRIVILEGED_MFA": "true",
                "SUPABASE_URL": "https://identity.mesh.invalid",
            }
        )
        environment = disposable_environment(config)
        envfile = work / "compose.env"
        envfile.write_text(
            "\n".join(k + "=" + v for k, v in config.items()) + "\n", encoding="utf-8"
        )
        base = [
            str(compose),
            "--project-directory",
            str(context),
            "--env-file",
            str(envfile),
            "-p",
            project,
            "-f",
            str(context / "docker-compose.yml"),
        ]
        stage = "compose_start"
        started = False
        ledger.write_text(
            json.dumps(
                {
                    "project": project,
                    "context": str(context),
                    "docker_host": environment.get("DOCKER_HOST", "default dedicated host"),
                }
            ),
            encoding="utf-8",
        )

        def run(command, label, timeout=300, input=None):
            # Keep raw logs in workspace only, never in delivered JSON evidence.
            logfile = workspace / (project + "-" + label + ".log")
            with logfile.open("wb") as stream:
                result = subprocess.run(
                    command,
                    cwd=context,
                    env=environment,
                    input=input,
                    stdout=stream,
                    stderr=subprocess.STDOUT,
                    timeout=timeout,
                )
            assert result.returncode == 0, label + " failed"
            return logfile.read_text(errors="replace").strip()

        try:
            run(base + ["config", "--quiet"], "compose_config")
            started = True
            if offline_wheels is not None or prebuilt_image is not None:
                image = prebuilt_image or project + "-backend:acceptance"
                if prebuilt_image is None:
                    stage = "api_image_build"
                    run(
                        [
                            str(docker),
                            "build",
                            "-f",
                            str(context / "infrastructure/docker/Dockerfile"),
                            "-t",
                            image,
                            str(context),
                        ],
                        "offline_api_image_build",
                        1800,
                    )
                stage = "current_source_and_dependency_equivalence"
                image = run(
                    [str(docker), "image", "inspect", "--format", "{{.Id}}", image],
                    "resolve_immutable_runtime_image",
                    30,
                )
                assert re.fullmatch(r"sha256:[a-f0-9]{64}", image)
                runtime_image_id = image
                source = ROOT / "backend/app"
                fingerprints = {
                    path.relative_to(source).as_posix(): hashlib.sha256(
                        path.read_bytes()
                    ).hexdigest()
                    for path in source.rglob("*.py")
                }
                versions = {
                    line.split("==")[0]: line.split("==")[1]
                    for line in (ROOT / "requirements.lock").read_text().splitlines()
                    if "==" in line and not line.startswith("#")
                }
                operational_files = [
                    *sorted((ROOT / "backend/migrations").rglob("*.py")),
                    ROOT / "scripts/bootstrap_role.py",
                    ROOT / "alembic.ini",
                    ROOT / "requirements.lock",
                    ROOT / "requirements-hashed.lock",
                    ROOT / "requirements-build.lock",
                    ROOT / "pyproject.toml",
                    ROOT / "supabase/supabase-ca.crt",
                ]
                operational = {
                    path.relative_to(ROOT).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
                    for path in operational_files
                }
                probe = (
                    "from pathlib import Path; import app,hashlib,importlib.metadata as m; roots=[Path('/srv/mesh/backend/app'),Path(app.__file__).resolve().parent]; expected="
                    + repr(fingerprints)
                    + "; assert all({p.relative_to(root).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob('*.py')}==expected for root in roots); versions="
                    + repr(versions)
                    + "; assert all(m.version(k)==v for k,v in versions.items())"
                    + "; operational="
                    + repr(operational)
                    + "; assert all(hashlib.sha256((Path('/srv/mesh')/name).read_bytes()).hexdigest()==digest for name,digest in operational.items())"
                )
                run(
                    [
                        str(docker),
                        "run",
                        "--rm",
                        "--pull=never",
                        "--network=none",
                        "--read-only",
                        "--user=10001:10001",
                        "--cap-drop=ALL",
                        "--security-opt=no-new-privileges",
                        "--entrypoint=python",
                        image,
                        "-c",
                        probe,
                    ],
                    "prebuilt_equivalence",
                    180,
                )
                checks[stage] = "passed"
                stage = "compose_start"
                references = run(
                    base + ["--profile", "*", "config", "--images"], "compose_image_references", 30
                ).splitlines()
                tags = [
                    reference for reference in references if reference.startswith(project + "-")
                ]
                assert tags, "Compose did not expose its generated backend image references"
                for reference in set(tags):
                    run(
                        [str(docker), "tag", image, reference],
                        "tag_" + reference.replace(":", "_"),
                        30,
                    )
                run(base + ["up", "--no-build", "-d", "api"], "compose_start", 1800)
            else:
                run(base + ["up", "--build", "-d", "api"], "compose_start", 3600)
            checks["actual_compose_postgresql_redis_mailpit_migrate_api_start"] = "passed"
            stage = "api_container_restrictions"
            api_container = run(base + ["ps", "-q", "api"], "api_container_id", 30)
            host_config = json.loads(
                run(
                    [str(docker), "inspect", "--format", "{{json .HostConfig}}", api_container],
                    "api_host_config",
                    30,
                )
            )
            assert host_config["ReadonlyRootfs"] is True
            assert "ALL" in host_config["CapDrop"]
            assert any(
                value.startswith("no-new-privileges") for value in host_config["SecurityOpt"]
            )
            assert not any("docker.sock" in bind for bind in (host_config.get("Binds") or []))
            assert all(
                binding["HostIp"] == "127.0.0.1"
                for bindings in host_config["PortBindings"].values()
                for binding in bindings
            )
            user = run(
                [str(docker), "inspect", "--format", "{{.Config.User}}", api_container],
                "api_user",
                30,
            )
            assert user == "10001"
            checks["actual_api_readonly_nonroot_caps_no_new_privileges_and_loopback_bind"] = (
                "passed"
            )
            stage = "api_readiness"
            probe = "import httpx; c=httpx.Client(timeout=5); assert c.get('http://127.0.0.1:8000/health/live').status_code==200; assert c.get('http://127.0.0.1:8000/health/ready').status_code==200; assert c.get('http://127.0.0.1:8000/api/v1/users/me/sessions').status_code==401"
            for attempt in range(30):
                try:
                    run(base + ["exec", "-T", "api", "python", "-c", probe], "readiness", 30)
                    break
                except AssertionError:
                    if attempt == 29:
                        raise
                    time.sleep(2)
            checks["actual_container_http_live_ready_and_anonymous_denial"] = "passed"
            stage = "bounded_http_concurrency_smoke"
            smoke = json.loads(
                run(
                    base + ["exec", "-T", "api", "python", "-", "--disposable-local-service"],
                    "http_concurrency_smoke",
                    120,
                    input=(ROOT / "scripts/verify_http_smoke.py").read_bytes(),
                )
            )
            assert smoke["passed"]
            smoke["verified_immutable_runtime_image_id"] = runtime_image_id
            (ROOT / "docs/http-concurrency-smoke-results.json").write_text(
                json.dumps(smoke, indent=2) + "\n", encoding="utf-8"
            )
            checks["actual_bounded_loopback_http_concurrency_smoke"] = "passed"
            stage = "worker_profiles"
            seed = f"INSERT INTO organizations(id,name,status,verification_status,created_at) VALUES ('{tenant}','Disposable Compose fixture','active','unverified',now());"
            run(
                base
                + [
                    "exec",
                    "-T",
                    "postgres",
                    "psql",
                    "-U",
                    "mesh_admin",
                    "-d",
                    "mesh",
                    "-v",
                    "ON_ERROR_STOP=1",
                ],
                "seed_parent",
                input=seed.encode(),
            )
            worker_health = {}
            for profile, service in [
                ("worker", "worker"),
                ("cloud", "cloud-worker"),
                ("documents", "retention"),
                ("billing", "billing-worker"),
            ]:
                run(
                    base + ["--profile", profile, "up", "--no-build", "-d", service],
                    "start_" + service,
                    180,
                )
                time.sleep(3)
                run(
                    base
                    + [
                        "exec",
                        "-T",
                        service,
                        "python",
                        "-c",
                        'from app.core.db import SessionFactory,assert_runtime_role; from sqlalchemy import text; s=SessionFactory(); assert_runtime_role(s); assert s.scalar(text("SELECT 1"))==1; s.close()',
                    ],
                    "restricted_" + service,
                    30,
                )
                kind = {
                    "worker": "outbox",
                    "cloud-worker": "cloud",
                    "retention": "retention",
                    "billing-worker": "billing",
                }[service]
                observation = json.loads(
                    run(
                        base
                        + [
                            "exec",
                            "-T",
                            service,
                            "python",
                            "-m",
                            "app.worker_health",
                            "--kind",
                            kind,
                            "--organization",
                            tenant,
                        ],
                        "heartbeat_" + service,
                        30,
                    )
                )
                assert observation["healthy"] and observation["completed_cycles"] >= 1
                container_id = run(base + ["ps", "-q", service], "health_container_" + service, 30)
                for _attempt in range(30):
                    health_state = run(
                        [
                            str(docker),
                            "inspect",
                            container_id,
                            "--format",
                            "{{.State.Health.Status}}",
                        ],
                        "container_health_" + service,
                        30,
                    )
                    if health_state == "healthy":
                        break
                    time.sleep(1)
                else:
                    raise AssertionError("Worker Docker healthcheck did not become healthy")
                worker_health[service] = observation
            checks["actual_outbox_cloud_retention_container_profiles_and_restricted_role"] = (
                "passed"
            )
            checks["actual_worker_heartbeat_cycle_and_container_healthchecks"] = "passed"
            (ROOT / "docs/worker-health-live-results.json").write_text(
                json.dumps(
                    {
                        "passed": True,
                        "verified_immutable_runtime_image_id": runtime_image_id,
                        "verified_app_source_fingerprint": app_source_fingerprint,
                        "workers": worker_health,
                        "limitations": [
                            "Actual outbox/cloud/retention/billing processes, private heartbeat files and Docker healthchecks on a disposable tenant with empty queues.",
                            "Not proof of external provider success, real job progress under load, or production alert routing. Scanner/OCR use the same monitor but were not launched as worker services by this driver.",
                        ],
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            stage = "disposable_backup_restore"
            restore_database = "mesh_test_restore_" + uuid4().hex
            run(
                base
                + [
                    "exec",
                    "-T",
                    "postgres",
                    "pg_dump",
                    "-U",
                    "mesh_admin",
                    "-Fc",
                    "-d",
                    "mesh",
                    "-f",
                    "/tmp/mesh-acceptance.dump",
                ],
                "dump_fixture_database",
                120,
            )
            run(
                base + ["exec", "-T", "postgres", "createdb", "-U", "mesh_admin", restore_database],
                "create_restore_database",
                30,
            )
            run(
                base
                + [
                    "exec",
                    "-T",
                    "postgres",
                    "pg_restore",
                    "-U",
                    "mesh_admin",
                    "-d",
                    restore_database,
                    "/tmp/mesh-acceptance.dump",
                ],
                "restore_fixture_database",
                120,
            )
            restored = run(
                base
                + [
                    "exec",
                    "-T",
                    "postgres",
                    "psql",
                    "-U",
                    "mesh_admin",
                    "-d",
                    restore_database,
                    "-tAc",
                    "SELECT version_num FROM alembic_version",
                ],
                "restored_migration",
                30,
            )
            assert restored == migration_head()
            restore_probe = (
                "SELECT json_build_object('tables', (SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' AND c.relkind='r'), "
                "'forced_rls_tables', (SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' AND c.relkind='r' AND c.relrowsecurity AND c.relforcerowsecurity), "
                "'policies', (SELECT count(*) FROM pg_policies WHERE schemaname='public'), "
                "'fixture', (SELECT count(*) FROM organizations WHERE id='" + tenant + "'))"
            )
            snapshots = []
            for target in ("mesh", restore_database):
                snapshots.append(
                    json.loads(
                        run(
                            base
                            + [
                                "exec",
                                "-T",
                                "postgres",
                                "psql",
                                "-U",
                                "mesh_admin",
                                "-d",
                                target,
                                "-tAc",
                                restore_probe,
                            ],
                            "restore_snapshot_" + target,
                            30,
                        )
                    )
                )
            assert snapshots[0] == snapshots[1]
            assert snapshots[1]["fixture"] == 1
            assert snapshots[1]["forced_rls_tables"] == 57
            assert snapshots[1]["policies"] >= 57
            (ROOT / "docs/compose-backup-restore-results.json").write_text(
                json.dumps(
                    {"passed": True, "revision": restored, "equivalent": True, **snapshots[1]},
                    indent=2,
                )
                + "\n"
            )
            checks["actual_disposable_schema_and_fixture_backup_restore"] = "passed"
            # Stop idle profiles to leave memory for the disposable PostgreSQL tests.
            run(
                base
                + [
                    "stop",
                    "worker",
                    "cloud-worker",
                    "billing-worker",
                    "retention",
                    "api",
                    "mailpit",
                    "redis",
                ],
                "stop_idle_services",
                120,
            )
            stage = "linux_postgresql_tests"
            image = run(base + ["images", "-q", "api"], "api_image", 30).splitlines()[0]
            run([str(docker), "tag", image, project + "-api:acceptance"], "tag_api", 30)
            test_context = work / "test-context"
            (test_context / "security-engine").mkdir(parents=True)
            for source in (ROOT / "backend/tests").rglob("*.py"):
                if source.is_symlink():
                    raise ValueError("Test source symlink is not permitted")
                target = test_context / "backend/tests" / source.relative_to(ROOT / "backend/tests")
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, target)
            for source in (ROOT / "scripts").glob("*.py"):
                if source.is_symlink():
                    raise ValueError("Verification script symlink is not permitted")
                target = test_context / "scripts" / source.name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, target)
            for source in (ROOT / "security-engine").iterdir():
                if (
                    source.name not in excluded
                    and not source.name.startswith(".env")
                    and source.is_file()
                ):
                    assert not source.is_symlink()
                    shutil.copyfile(source, test_context / "security-engine" / source.name)
            shutil.copytree(ROOT / "supabase/migrations", test_context / "supabase/migrations")
            (test_context / "docs").mkdir()
            shutil.copyfile(
                ROOT / "docs/dependency-hash-lock-results.json",
                test_context / "docs/dependency-hash-lock-results.json",
            )
            testdocker = test_context / "Dockerfile.acceptance"
            pytest_version = importlib.metadata.version("pytest")
            offline_options = (
                "--no-index --find-links=/opt/mesh/wheels " if offline_wheels is not None else ""
            )
            wheel_copy = ""
            if offline_wheels is not None:
                shutil.copytree(
                    context / ".runtime-wheelhouse", test_context / ".runtime-wheelhouse"
                )
                wheel_copy = "COPY .runtime-wheelhouse /opt/mesh/wheels\n"
            testdocker.write_text(
                f"FROM {project}-api:acceptance\nUSER root\nCOPY security-engine ./security-engine\nCOPY backend/tests ./backend/tests\nCOPY scripts ./scripts\nCOPY docs ./docs\nCOPY supabase/migrations ./supabase/migrations\n{wheel_copy}RUN pip install --no-cache-dir {offline_options}pytest=={pytest_version} bandit==1.9.4\nUSER 10001\n",
                encoding="utf-8",
            )
            run(
                [
                    str(docker),
                    "build",
                    "-f",
                    str(testdocker),
                    "-t",
                    project + "-tests:acceptance",
                    str(test_context),
                ],
                "build_linux_tests",
                1200,
            )
            database = "mesh_test_" + uuid4().hex
            run(
                base
                + [
                    "exec",
                    "-T",
                    "postgres",
                    "psql",
                    "-U",
                    "mesh_admin",
                    "-d",
                    "mesh",
                    "-v",
                    "ON_ERROR_STOP=1",
                ],
                "create_test_database",
                input=f"CREATE DATABASE {database};".encode(),
            )
            testenv = work / "tests.env"
            testenv.write_text(
                "MESH_POSTGRES_ADMIN_URL=postgresql+psycopg://mesh_admin:"
                + config["POSTGRES_ADMIN_PASSWORD"]
                + "@postgres:5432/"
                + database
                + "\nAUTH_RATE_SECRET="
                + config["AUTH_RATE_SECRET"]
                + "\n",
                encoding="utf-8",
            )
            # Count actual PostgreSQL passes from the verbose Linux test output.
            command = [
                str(docker),
                "run",
                "--rm",
                "--name",
                project + "-tests",
                "--label",
                "mesh.acceptance.project=" + project,
                "--network",
                project + "_default",
                "--env-file",
                str(testenv),
                project + "-tests:acceptance",
                "python",
                "-m",
                "pytest",
                "-vv",
                "-o",
                "faulthandler_timeout=45",
                "-p",
                "no:cacheprovider",
                "--basetemp=/tmp/mesh-pytest",
            ]
            linux_output = run(command, "linux_and_postgresql_tests", 600)
            passed_counts = re.findall(r"\b(\d+) passed\b", linux_output)
            skipped_counts = re.findall(r"\b(\d+) skipped\b", linux_output)
            assert passed_counts, "Linux suite did not emit a test summary"
            postgresql_cases = len(
                re.findall(
                    r"^backend/tests/test_postgres_integration\.py::[^\r\n]+ PASSED(?: |$)",
                    linux_output,
                    re.MULTILINE,
                )
            )
            assert postgresql_cases > 0, "No actual PostgreSQL cases were observed"
            (ROOT / "docs/linux-test-results.json").write_text(
                json.dumps(
                    {
                        "passed": int(passed_counts[-1]),
                        "skipped": int(skipped_counts[-1]) if skipped_counts else 0,
                        "failed": 0,
                        "platform": "Linux",
                        "live_disposable_postgresql_cases": postgresql_cases,
                        "limitations": [
                            "Docker scanner and Supabase Storage opt-in pytest cases remain skipped; separate service evidence is recorded elsewhere."
                        ],
                    },
                    indent=2,
                )
                + "\n"
            )
            checks["actual_linux_suite_and_disposable_postgresql_cases"] = "passed"
        except Exception as error:
            checks[stage] = "failed: " + type(error).__name__
        finally:
            if started:
                try:
                    runners = run(
                        [
                            str(docker),
                            "ps",
                            "-a",
                            "--filter",
                            "label=mesh.acceptance.project=" + project,
                            "--format",
                            "{{.ID}}",
                        ],
                        "owned_test_runners",
                        30,
                    ).splitlines()
                    for runner in runners:
                        details = json.loads(
                            run([str(docker), "inspect", runner], "test_runner_ownership", 30)
                        )[0]
                        assert details["Config"]["Labels"]["mesh.acceptance.project"] == project
                        run([str(docker), "rm", "-f", runner], "test_runner_cleanup", 30)
                    # project is generated above, never accepted from user input.
                    run(
                        base
                        + [
                            "--profile",
                            "worker",
                            "--profile",
                            "cloud",
                            "--profile",
                            "documents",
                            "--profile",
                            "billing",
                            "down",
                            "--volumes",
                            "--remove-orphans",
                        ],
                        "cleanup",
                        180,
                    )
                    image_tags = run(
                        [str(docker), "image", "ls", "--format", "{{.Repository}}:{{.Tag}}"],
                        "image_cleanup_inventory",
                        30,
                    ).splitlines()
                    for tag in owned_image_tags(project, image_tags):
                        run(
                            [str(docker), "image", "rm", tag],
                            "image_cleanup_" + tag.replace(":", "_"),
                            60,
                        )
                    checks["own_compose_project_resources_removed"] = "passed"
                    ledger.unlink()
                except Exception as error:
                    checks["cleanup"] = "failed: " + type(error).__name__
            else:
                ledger.unlink()
    return {
        "checks": checks,
        "passed": all(value == "passed" for value in checks.values()),
        "backend_image": prebuilt_image,
        "verified_immutable_runtime_image_id": runtime_image_id,
        "verified_app_source_fingerprint": app_source_fingerprint,
        "limitations": [
            (
                "With a prebuilt runtime, this driver adds the offline wheel cache only to its disposable Linux test image; runtime image provenance is recorded separately."
                if prebuilt_image is not None
                else "Offline runtime build adds a public cache COPY and pip --no-index; the online production build path is separate."
            )
            if offline_wheels is not None
            else "Online package installation path selected.",
            "Disposable dedicated Docker host only; hosted credentials/data not used.",
            "A synthetic identity URL satisfies the readiness configuration check only; no provider request is made. Actual Supabase Auth/MFA/Storage acceptance is recorded separately.",
            "A prebuilt image was used only after exact API source and locked package-version checks."
            if prebuilt_image
            else "Backend image built during this run.",
            "ClamAV image is not started by this acceptance driver; signed-definition native engine verified separately.",
            "Empty worker queues verify container startup and restricted database connectivity, not external cloud or SCIM mutations.",
        ],
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--docker-executable", type=Path, required=True)
    parser.add_argument("--compose-executable", type=Path, required=True)
    parser.add_argument("--dedicated-disposable-docker-host", action="store_true")
    parser.add_argument("--offline-wheels", type=Path)
    parser.add_argument("--prebuilt-backend-image")
    args = parser.parse_args()
    try:
        report = verify(
            args.docker_executable,
            args.compose_executable,
            args.dedicated_disposable_docker_host,
            args.offline_wheels,
            args.prebuilt_backend_image,
        )
    except Exception as error:
        print(json.dumps({"failed": type(error).__name__}))
        raise SystemExit(1) from None
    (ROOT / "docs/docker-runtime-results.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, indent=2))
    raise SystemExit(0 if report["passed"] else 1)
