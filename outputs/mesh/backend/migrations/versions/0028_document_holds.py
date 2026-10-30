"""Audited identity document preservation and independent hold release."""

import sqlalchemy as sa
from alembic import op

revision = "0028"
down_revision = "0027"


def upgrade():
    with op.batch_alter_table("identity_documents") as batch:
        batch.create_unique_constraint("uq_identity_document_tenant_id", ["organization_id", "id"])
    op.create_table(
        "document_holds",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("document_id", sa.String(36), nullable=False),
        sa.Column("request_key", sa.String(36), nullable=False),
        sa.Column("reason_code", sa.String(30), nullable=False),
        sa.Column("placed_by", sa.String(36), nullable=False),
        sa.Column("released_at", sa.DateTime(timezone=True)),
        sa.Column("released_by", sa.String(36)),
        sa.Column("release_reason", sa.String(30)),
        sa.ForeignKeyConstraint(
            ["organization_id", "document_id"],
            ["identity_documents.organization_id", "identity_documents.id"],
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "placed_by"], ["memberships.organization_id", "memberships.user_id"]
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "released_by"],
            ["memberships.organization_id", "memberships.user_id"],
        ),
        sa.UniqueConstraint("organization_id", "request_key", name="uq_document_hold_request"),
        sa.CheckConstraint("length(request_key)=36", name="ck_document_hold_request"),
        sa.CheckConstraint(
            "reason_code IN ('dispute','investigation','regulatory','other')",
            name="ck_document_hold_reason",
        ),
        sa.CheckConstraint(
            "(released_at IS NULL AND released_by IS NULL AND release_reason IS NULL) OR (released_at IS NOT NULL AND released_by IS NOT NULL AND released_by != placed_by AND released_at >= created_at AND release_reason IS NOT NULL AND release_reason IN ('resolved','entered_in_error','other'))",
            name="ck_document_hold_release",
        ),
    )
    op.create_index("ix_document_holds_organization_id", "document_holds", ["organization_id"])
    op.create_index(
        "ix_document_hold_active",
        "document_holds",
        ["organization_id", "document_id", "released_at"],
    )
    op.create_index(
        "uq_document_active_hold",
        "document_holds",
        ["organization_id", "document_id"],
        unique=True,
        postgresql_where=sa.text("released_at IS NULL"),
        sqlite_where=sa.text("released_at IS NULL"),
    )
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute('ALTER TABLE "document_holds" ENABLE ROW LEVEL SECURITY')
    op.execute('ALTER TABLE "document_holds" FORCE ROW LEVEL SECURITY')
    op.execute("""CREATE POLICY tenant_boundary ON "document_holds"
        USING (organization_id = nullif(current_setting('mesh.organization_id',true),''))
        WITH CHECK (organization_id = nullif(current_setting('mesh.organization_id',true),''))""")
    op.execute("""CREATE FUNCTION mesh_guard_document_hold() RETURNS trigger LANGUAGE plpgsql
      SET search_path = pg_catalog, public AS $$
      DECLARE document_status text;
      BEGIN
        IF TG_OP='INSERT' THEN
          SELECT status INTO document_status FROM public.identity_documents
            WHERE organization_id=NEW.organization_id AND id=NEW.document_id FOR UPDATE;
          IF document_status IS NULL OR document_status='deleted' OR NEW.released_at IS NOT NULL THEN
            RAISE EXCEPTION 'Hold requires a retained document and active admission';
          END IF;
          IF EXISTS (SELECT 1 FROM public.document_holds WHERE organization_id=NEW.organization_id
            AND document_id=NEW.document_id AND released_at IS NULL) THEN
            RAISE EXCEPTION 'Document already has an active hold';
          END IF;
          RETURN NEW;
        END IF;
        IF OLD.released_at IS NOT NULL OR NEW.released_at IS NULL OR
          ROW(NEW.id,NEW.organization_id,NEW.created_at,NEW.document_id,NEW.request_key,NEW.reason_code,NEW.placed_by)
          IS DISTINCT FROM ROW(OLD.id,OLD.organization_id,OLD.created_at,OLD.document_id,OLD.request_key,OLD.reason_code,OLD.placed_by)
        THEN RAISE EXCEPTION 'Hold evidence is immutable except one independent release'; END IF;
        RETURN NEW;
      END $$""")
    op.execute("""CREATE FUNCTION mesh_guard_held_document() RETURNS trigger LANGUAGE plpgsql
      SET search_path = pg_catalog, public AS $$
      BEGIN
        IF EXISTS (SELECT 1 FROM public.document_holds WHERE organization_id=OLD.organization_id
          AND document_id=OLD.id AND released_at IS NULL) THEN
          IF TG_OP='DELETE' THEN RAISE EXCEPTION 'Held document cannot be deleted'; END IF;
          IF ROW(NEW.id,NEW.organization_id,NEW.employee_id,NEW.storage_key,NEW.media_type,NEW.digest,NEW.expires_at,NEW.ocr_ciphertext)
            IS DISTINCT FROM ROW(OLD.id,OLD.organization_id,OLD.employee_id,OLD.storage_key,OLD.media_type,OLD.digest,OLD.expires_at,OLD.ocr_ciphertext)
            OR NEW.status='deleted' THEN RAISE EXCEPTION 'Held document preservation is immutable'; END IF;
        END IF;
        IF TG_OP='DELETE' THEN RETURN OLD; END IF;
        RETURN NEW;
      END $$""")
    op.execute(
        "CREATE TRIGGER document_hold_guard BEFORE INSERT OR UPDATE ON document_holds FOR EACH ROW EXECUTE FUNCTION mesh_guard_document_hold()"
    )
    op.execute(
        "CREATE TRIGGER no_document_hold_delete BEFORE DELETE ON document_holds FOR EACH ROW EXECUTE FUNCTION mesh_deny_ledger_mutation()"
    )
    op.execute(
        "CREATE TRIGGER held_document_guard BEFORE UPDATE OR DELETE ON identity_documents FOR EACH ROW EXECUTE FUNCTION mesh_guard_held_document()"
    )
    op.execute("REVOKE ALL ON TABLE document_holds FROM PUBLIC")
    for function in ("mesh_guard_document_hold", "mesh_guard_held_document"):
        op.execute(f"REVOKE ALL ON FUNCTION {function}() FROM PUBLIC")
    for role in ("anon", "authenticated", "service_role"):
        op.execute(f"""DO $hold_acl$ BEGIN
          IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname='{role}') THEN
            REVOKE ALL ON TABLE document_holds FROM {role};
            REVOKE ALL ON FUNCTION mesh_guard_document_hold(),mesh_guard_held_document() FROM {role};
          END IF;
        END $hold_acl$""")
    op.execute("""DO $hold_runtime$ BEGIN
      IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname='mesh_runtime') THEN
        GRANT SELECT,INSERT,UPDATE ON TABLE document_holds TO mesh_runtime;
        REVOKE DELETE ON TABLE document_holds FROM mesh_runtime;
      END IF;
    END $hold_runtime$""")


def downgrade():
    raise RuntimeError("Document hold evidence requires a reviewed recovery migration")
