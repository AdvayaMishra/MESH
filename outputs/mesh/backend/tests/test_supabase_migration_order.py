import re
from datetime import datetime
from pathlib import Path


def test_frozen_supabase_migrations_have_unique_chronological_cli_versions():
    folder = Path(__file__).resolve().parents[2] / "supabase/migrations"
    paths = sorted(folder.glob("*.sql"))
    versions = []
    for path in paths:
        match = re.fullmatch(r"([0-9]{14})_[a-z0-9_]+\.sql", path.name)
        assert match, f"Supabase CLI migration needs a chronological version: {path.name}"
        versions.append(match[1])
        datetime.strptime(match[1], "%Y%m%d%H%M%S")
    assert len(versions) == len(set(versions))
    assert paths[0].name == "20261023000100_mesh_fresh_project.sql"
    assert "CREATE TABLE organizations" in paths[0].read_text(encoding="utf-8")
    assert paths[-1].name == "20261030000100_membership_discovery.sql"
