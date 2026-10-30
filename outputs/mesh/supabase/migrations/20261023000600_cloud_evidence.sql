-- Running upgrade 0007 -> 0008

ALTER TABLE cloud_assessments ADD COLUMN errors JSON;

ALTER TABLE cloud_assessments ADD COLUMN coverage JSON;

ALTER TABLE cloud_assessments ADD COLUMN limitations JSON;

CREATE TRIGGER append_only BEFORE UPDATE OR DELETE ON cloud_assessments FOR EACH ROW EXECUTE FUNCTION mesh_deny_ledger_mutation();

UPDATE alembic_version SET version_num='0008' WHERE alembic_version.version_num = '0007';


