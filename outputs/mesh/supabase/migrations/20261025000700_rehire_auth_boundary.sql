BEGIN;

-- Running upgrade 0018 -> 0019

ALTER TABLE memberships ADD COLUMN access_not_before TIMESTAMP WITH TIME ZONE;

UPDATE alembic_version SET version_num='0019' WHERE alembic_version.version_num = '0018';

COMMIT;

