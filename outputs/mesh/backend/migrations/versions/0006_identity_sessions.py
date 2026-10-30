"""Durable self-owned session metadata and immediate MESH session revocation."""

import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"


def upgrade():
    op.create_table(
        "identity_sessions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("provider_session_id", sa.String(36), nullable=False),
        sa.Column("client_hint", sa.String(200), nullable=False),
        sa.Column("ip_digest", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revocation_reason", sa.String(40), nullable=True),
        sa.UniqueConstraint("user_id", "provider_session_id"),
    )
    op.create_index("ix_identity_sessions_user_id", "identity_sessions", ["user_id"])
    if op.get_bind().dialect.name == "postgresql":
        op.execute('ALTER TABLE "identity_sessions" ENABLE ROW LEVEL SECURITY')
        op.execute('ALTER TABLE "identity_sessions" FORCE ROW LEVEL SECURITY')
        op.execute("""CREATE POLICY tenant_boundary ON "identity_sessions"
            USING (user_id = nullif(current_setting('mesh.user_id',true),''))
            WITH CHECK (user_id = nullif(current_setting('mesh.user_id',true),''))""")
        for role in ("anon", "authenticated"):
            op.execute(f"""DO $mesh_session_grants$ BEGIN
                IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='{role}') THEN
                    REVOKE ALL ON TABLE public.identity_sessions FROM {role};
                END IF;
            END; $mesh_session_grants$;""")


def downgrade():
    raise RuntimeError("Destructive downgrade requires a reviewed recovery migration")
