BEGIN;

-- Running upgrade 0027 -> 0028

ALTER TABLE identity_documents ADD CONSTRAINT uq_identity_document_tenant_id UNIQUE (organization_id, id);

CREATE TABLE document_holds (
    id VARCHAR(36) NOT NULL, 
    organization_id VARCHAR(36) NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    document_id VARCHAR(36) NOT NULL, 
    request_key VARCHAR(36) NOT NULL, 
    reason_code VARCHAR(30) NOT NULL, 
    placed_by VARCHAR(36) NOT NULL, 
    released_at TIMESTAMP WITH TIME ZONE, 
    released_by VARCHAR(36), 
    release_reason VARCHAR(30), 
    PRIMARY KEY (id), 
    FOREIGN KEY(organization_id, document_id) REFERENCES identity_documents (organization_id, id), 
    FOREIGN KEY(organization_id, placed_by) REFERENCES memberships (organization_id, user_id), 
    FOREIGN KEY(organization_id, released_by) REFERENCES memberships (organization_id, user_id), 
    CONSTRAINT uq_document_hold_request UNIQUE (organization_id, request_key), 
    CONSTRAINT ck_document_hold_request CHECK (length(request_key)=36), 
    CONSTRAINT ck_document_hold_reason CHECK (reason_code IN ('dispute','investigation','regulatory','other')), 
    CONSTRAINT ck_document_hold_release CHECK ((released_at IS NULL AND released_by IS NULL AND release_reason IS NULL) OR (released_at IS NOT NULL AND released_by IS NOT NULL AND released_by != placed_by AND released_at >= created_at AND release_reason IS NOT NULL AND release_reason IN ('resolved','entered_in_error','other')))
);

CREATE INDEX ix_document_holds_organization_id ON document_holds (organization_id);

CREATE INDEX ix_document_hold_active ON document_holds (organization_id, document_id, released_at);

CREATE UNIQUE INDEX uq_document_active_hold ON document_holds (organization_id, document_id) WHERE released_at IS NULL;

ALTER TABLE "document_holds" ENABLE ROW LEVEL SECURITY;

ALTER TABLE "document_holds" FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_boundary ON "document_holds"
        USING (organization_id = nullif(current_setting('mesh.organization_id',true),''))
        WITH CHECK (organization_id = nullif(current_setting('mesh.organization_id',true),''));

CREATE FUNCTION mesh_guard_document_hold() RETURNS trigger LANGUAGE plpgsql
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
      END $$;

CREATE FUNCTION mesh_guard_held_document() RETURNS trigger LANGUAGE plpgsql
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
      END $$;

CREATE TRIGGER document_hold_guard BEFORE INSERT OR UPDATE ON document_holds FOR EACH ROW EXECUTE FUNCTION mesh_guard_document_hold();

CREATE TRIGGER no_document_hold_delete BEFORE DELETE ON document_holds FOR EACH ROW EXECUTE FUNCTION mesh_deny_ledger_mutation();

CREATE TRIGGER held_document_guard BEFORE UPDATE OR DELETE ON identity_documents FOR EACH ROW EXECUTE FUNCTION mesh_guard_held_document();

REVOKE ALL ON TABLE document_holds FROM PUBLIC;

REVOKE ALL ON FUNCTION mesh_guard_document_hold() FROM PUBLIC;

REVOKE ALL ON FUNCTION mesh_guard_held_document() FROM PUBLIC;

DO $hold_acl$ BEGIN
          IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname='anon') THEN
            REVOKE ALL ON TABLE document_holds FROM anon;
            REVOKE ALL ON FUNCTION mesh_guard_document_hold(),mesh_guard_held_document() FROM anon;
          END IF;
        END $hold_acl$;

DO $hold_acl$ BEGIN
          IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname='authenticated') THEN
            REVOKE ALL ON TABLE document_holds FROM authenticated;
            REVOKE ALL ON FUNCTION mesh_guard_document_hold(),mesh_guard_held_document() FROM authenticated;
          END IF;
        END $hold_acl$;

DO $hold_acl$ BEGIN
          IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname='service_role') THEN
            REVOKE ALL ON TABLE document_holds FROM service_role;
            REVOKE ALL ON FUNCTION mesh_guard_document_hold(),mesh_guard_held_document() FROM service_role;
          END IF;
        END $hold_acl$;

DO $hold_runtime$ BEGIN
      IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname='mesh_runtime') THEN
        GRANT SELECT,INSERT,UPDATE ON TABLE document_holds TO mesh_runtime;
        REVOKE DELETE ON TABLE document_holds FROM mesh_runtime;
      END IF;
    END $hold_runtime$;

UPDATE alembic_version SET version_num='0028' WHERE alembic_version.version_num = '0027';

COMMIT;

