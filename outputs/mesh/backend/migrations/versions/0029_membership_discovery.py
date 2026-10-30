"""Self membership discovery without cross-tenant business-data access."""

from alembic import op

revision = "0029"
down_revision = "0028"


def upgrade():
    op.create_index("ix_memberships_user_org", "memberships", ["user_id", "organization_id"])
    if op.get_bind().dialect.name == "postgresql":
        op.execute("""CREATE POLICY self_membership_discovery ON memberships FOR SELECT
            USING (
                nullif(current_setting('mesh.organization_id', true), '') IS NULL
                AND user_id = nullif(current_setting('mesh.user_id', true), '')
                AND active
            )""")


def downgrade():
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP POLICY self_membership_discovery ON memberships")
    op.drop_index("ix_memberships_user_org", table_name="memberships")
