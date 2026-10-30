-- Running upgrade 0011 -> 0012

ALTER TABLE employment_changes ADD COLUMN resolution_reason VARCHAR(1000);

ALTER TABLE employment_changes ADD COLUMN resolved_at TIMESTAMP WITH TIME ZONE;

UPDATE alembic_version SET version_num='0012' WHERE alembic_version.version_num = '0011';


