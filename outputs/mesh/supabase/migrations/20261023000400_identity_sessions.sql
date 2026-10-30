-- Running upgrade 0005 -> 0006

CREATE TABLE identity_sessions (
    id VARCHAR(36) NOT NULL, 
    user_id VARCHAR(36) NOT NULL, 
    provider_session_id VARCHAR(36) NOT NULL, 
    client_hint VARCHAR(200) NOT NULL, 
    ip_digest VARCHAR(64) NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    last_seen TIMESTAMP WITH TIME ZONE NOT NULL, 
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    revoked_at TIMESTAMP WITH TIME ZONE, 
    revocation_reason VARCHAR(40), 
    PRIMARY KEY (id), 
    UNIQUE (user_id, provider_session_id)
);

CREATE INDEX ix_identity_sessions_user_id ON identity_sessions (user_id);

ALTER TABLE "identity_sessions" ENABLE ROW LEVEL SECURITY;

ALTER TABLE "identity_sessions" FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_boundary ON "identity_sessions"
            USING (user_id = nullif(current_setting('mesh.user_id',true),''))
            WITH CHECK (user_id = nullif(current_setting('mesh.user_id',true),''));

DO $mesh_session_grants$ BEGIN
                IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='anon') THEN
                    REVOKE ALL ON TABLE public.identity_sessions FROM anon;
                END IF;
            END; $mesh_session_grants$;;

DO $mesh_session_grants$ BEGIN
                IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='authenticated') THEN
                    REVOKE ALL ON TABLE public.identity_sessions FROM authenticated;
                END IF;
            END; $mesh_session_grants$;;

UPDATE alembic_version SET version_num='0006' WHERE alembic_version.version_num = '0005';


