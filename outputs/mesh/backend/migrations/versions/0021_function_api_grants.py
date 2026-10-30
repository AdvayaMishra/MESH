"""Remove Supabase default API grants from narrow backend security-definer functions."""

from alembic import op

revision = "0021"
down_revision = "0020"


def upgrade():
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute("""
        REVOKE ALL ON FUNCTION public.mesh_retire_telemetry(integer,integer) FROM PUBLIC;
        REVOKE ALL ON FUNCTION public.mesh_rehire_clear_project_grants(text) FROM PUBLIC;
        DO $mesh_function_acl$
        DECLARE api_role text;
        BEGIN
            FOR api_role IN SELECT rolname FROM pg_roles WHERE rolname IN ('anon','authenticated','service_role') LOOP
                EXECUTE 'REVOKE ALL ON FUNCTION public.mesh_retire_telemetry(integer,integer) FROM ' || quote_ident(api_role);
                EXECUTE 'REVOKE ALL ON FUNCTION public.mesh_rehire_clear_project_grants(text) FROM ' || quote_ident(api_role);
            END LOOP;
        END $mesh_function_acl$;
    """)


def downgrade():
    raise RuntimeError("Restoring API execution of backend-only functions requires security review")
