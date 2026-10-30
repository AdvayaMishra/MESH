"""Add immutable, tenant-bound normalized cloud context to existing assessments."""

import sqlalchemy as sa
from alembic import op

revision = "0026"
down_revision = "0025"


def upgrade():
    op.add_column(
        "cloud_assessments",
        sa.Column("normalized_context", sa.JSON(none_as_null=True), nullable=True),
    )
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute("""ALTER TABLE cloud_assessments ADD CONSTRAINT ck_cloud_context_envelope CHECK (
        normalized_context IS NULL OR (
          octet_length(normalized_context::text) <= 8388608
          AND COALESCE(json_typeof(normalized_context) = 'object',false)
          AND COALESCE(normalized_context->'envelope'->>'contract' = 'mesh.cloud-context',false)
          AND COALESCE(normalized_context->'envelope'->>'schema_version' = '1.0.0',false)
          AND COALESCE(normalized_context->'envelope'->>'publication_state' = 'sealed',false)
          AND COALESCE(normalized_context->'envelope'->>'organization_id' = organization_id,false)
          AND COALESCE(normalized_context->'envelope'->>'assessment_id' = id,false)
          AND COALESCE(normalized_context->'envelope'->'scope'->>'organization_id' = organization_id,false)
          AND COALESCE(json_typeof(normalized_context->'assets') = 'array',false)
          AND COALESCE(json_typeof(normalized_context->'principals') = 'array',false)
          AND COALESCE(json_typeof(normalized_context->'permissions') = 'array',false)
          AND COALESCE(json_typeof(normalized_context->'relationships') = 'array',false)
          AND COALESCE(json_typeof(normalized_context->'evidence') = 'array',false)
        ))""")
    op.execute("""CREATE FUNCTION mesh_guard_cloud_context_job() RETURNS trigger LANGUAGE plpgsql
      SET search_path = pg_catalog, public AS $$
      DECLARE job_id text;
      BEGIN
        job_id := NEW.normalized_context->'envelope'->>'source_job_id';
        IF job_id IS NOT NULL AND NOT EXISTS (
          SELECT 1 FROM public.cloud_assessment_jobs j
          WHERE j.organization_id=NEW.organization_id AND j.id=job_id
            AND j.assessment_id=NEW.id AND j.status='completed'
        ) THEN RAISE EXCEPTION 'Cloud context job linkage is invalid'; END IF;
        RETURN NEW;
      END $$""")
    op.execute("""CREATE CONSTRAINT TRIGGER cloud_context_job_link
      AFTER INSERT ON cloud_assessments DEFERRABLE INITIALLY DEFERRED
      FOR EACH ROW EXECUTE FUNCTION mesh_guard_cloud_context_job()""")
    op.execute("REVOKE ALL ON FUNCTION mesh_guard_cloud_context_job() FROM PUBLIC")
    op.execute("REVOKE ALL ON TABLE cloud_assessments FROM PUBLIC")
    for role in ("anon", "authenticated", "service_role"):
        op.execute(f"""DO $cloud_acl$ BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='{role}') THEN
            REVOKE ALL ON FUNCTION mesh_guard_cloud_context_job() FROM {role};
            REVOKE ALL ON TABLE cloud_assessments FROM {role};
          END IF;
        END $cloud_acl$""")
    op.execute("""DO $cloud_runtime$ BEGIN
      IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='mesh_runtime') THEN
        GRANT SELECT,INSERT ON TABLE cloud_assessments TO mesh_runtime;
        REVOKE UPDATE,DELETE ON TABLE cloud_assessments FROM mesh_runtime;
      END IF;
    END $cloud_runtime$""")
    # Existing forced RLS and append_only trigger cover the new column.


def downgrade():
    raise RuntimeError("Cloud evidence retirement requires a reviewed recovery migration")
