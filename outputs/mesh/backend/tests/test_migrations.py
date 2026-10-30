import os
import subprocess
import sys
from pathlib import Path

from app.core.db import Base
from sqlalchemy import create_engine, inspect

ROOT = Path(__file__).resolve().parents[2]


def test_postgres_migration_emits_all_tenant_policies():
    environment = {
        **os.environ,
        "TEST_MODE": "false",
        "DATABASE_URL": "postgresql+psycopg://offline:unused@localhost/mesh",
    }
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head", "--sql"],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        timeout=30,
        check=True,
    )
    for name in Base.metadata.tables:
        assert f'ALTER TABLE "{name}" ENABLE ROW LEVEL SECURITY' in result.stdout
        assert f'ALTER TABLE "{name}" FORCE ROW LEVEL SECURITY' in result.stdout
        assert f'CREATE POLICY tenant_boundary ON "{name}"' in result.stdout
    assert "CREATE TRIGGER append_only" in result.stdout


def test_frozen_migration_creates_sqlite_schema(tmp_path):
    database_url = "sqlite:///" + (tmp_path / "migrations.db").as_posix()
    environment = {**os.environ, "TEST_MODE": "true", "DATABASE_URL": database_url}
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        timeout=30,
        check=True,
    )
    engine = create_engine(database_url)
    assert set(inspect(engine).get_table_names()) == set(Base.metadata.tables) | {"alembic_version"}
    engine.dispose()
