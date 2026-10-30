BEGIN;

-- Running upgrade 0016 -> 0017

CREATE TRIGGER immutable_observation BEFORE UPDATE ON security_events FOR EACH ROW EXECUTE FUNCTION mesh_deny_ledger_mutation();

DO $mesh_immutable_observation$ BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='mesh_runtime') THEN
                REVOKE UPDATE, DELETE ON TABLE public.security_events FROM mesh_runtime;
            END IF;
        END; $mesh_immutable_observation$;;

CREATE TRIGGER immutable_observation BEFORE UPDATE ON anomalies FOR EACH ROW EXECUTE FUNCTION mesh_deny_ledger_mutation();

DO $mesh_immutable_observation$ BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='mesh_runtime') THEN
                REVOKE UPDATE, DELETE ON TABLE public.anomalies FROM mesh_runtime;
            END IF;
        END; $mesh_immutable_observation$;;

UPDATE alembic_version SET version_num='0017' WHERE alembic_version.version_num = '0016';

COMMIT;

