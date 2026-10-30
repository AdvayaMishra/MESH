-- Running upgrade 0004 -> 0005

ALTER TABLE ai_usage ADD COLUMN model VARCHAR(100);

ALTER TABLE ai_usage ADD COLUMN billing_currency VARCHAR(3);

ALTER TABLE ai_usage ADD COLUMN pricing JSON;

UPDATE alembic_version SET version_num='0005' WHERE alembic_version.version_num = '0004';


