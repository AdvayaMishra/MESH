BEGIN;

-- Running upgrade 0012 -> 0013

ALTER TABLE leave_entitlements ADD COLUMN holidays JSON DEFAULT '[]' NOT NULL;

UPDATE alembic_version SET version_num='0013' WHERE alembic_version.version_num = '0012';

COMMIT;

