"""Deny observation mutation while preserving narrowly scoped retirement deletion."""

from alembic import op

revision = "0017"
down_revision = "0016"


def upgrade():
    if op.get_bind().dialect.name != "postgresql":
        return
    for table in ("security_events", "anomalies"):
        op.execute(
            f"CREATE TRIGGER immutable_observation BEFORE UPDATE ON {table} FOR EACH ROW EXECUTE FUNCTION mesh_deny_ledger_mutation()"
        )
        op.execute(f"""DO $mesh_immutable_observation$ BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='mesh_runtime') THEN
                REVOKE UPDATE, DELETE ON TABLE public.{table} FROM mesh_runtime;
            END IF;
        END; $mesh_immutable_observation$;""")


def downgrade():
    raise RuntimeError("Observation immutability changes require a reviewed recovery migration")
