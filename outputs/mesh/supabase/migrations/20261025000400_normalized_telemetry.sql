BEGIN;

-- Running upgrade 0015 -> 0016

ALTER TABLE security_events ADD COLUMN context JSON DEFAULT '{}' NOT NULL;

CREATE INDEX ix_event_org_category_time ON security_events (organization_id, category, occurred_at, id);

UPDATE alembic_version SET version_num='0016' WHERE alembic_version.version_num = '0015';

COMMIT;

