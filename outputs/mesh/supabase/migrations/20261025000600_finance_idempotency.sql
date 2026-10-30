BEGIN;

-- Running upgrade 0017 -> 0018

ALTER TABLE cost_records ADD COLUMN request_key VARCHAR(36);

ALTER TABLE cost_records ADD COLUMN request_digest VARCHAR(64);

ALTER TABLE cost_records ADD COLUMN recorded_by VARCHAR(36);

ALTER TABLE cost_records ADD COLUMN billing_provider VARCHAR(10);

ALTER TABLE cost_records ADD COLUMN usage_quantity NUMERIC(20, 6);

ALTER TABLE cost_records ADD COLUMN usage_unit VARCHAR(20);

ALTER TABLE cost_records ADD CONSTRAINT uq_cost_request_key UNIQUE (organization_id, request_key);

ALTER TABLE cost_records ADD CONSTRAINT fk_cost_actor_tenant FOREIGN KEY(organization_id, recorded_by) REFERENCES memberships (organization_id, user_id);

ALTER TABLE cost_records ADD CONSTRAINT ck_cost_receipt_complete CHECK ((request_key IS NULL AND request_digest IS NULL AND recorded_by IS NULL) OR (request_key IS NOT NULL AND request_digest IS NOT NULL AND recorded_by IS NOT NULL));

ALTER TABLE cost_records ADD CONSTRAINT ck_cost_request_key_length CHECK (request_key IS NULL OR length(request_key)=36);

ALTER TABLE cost_records ADD CONSTRAINT ck_cost_digest_length CHECK (request_digest IS NULL OR length(request_digest)=64);

ALTER TABLE cost_records ADD CONSTRAINT ck_cost_usage_pair CHECK ((usage_quantity IS NULL AND usage_unit IS NULL) OR (usage_quantity IS NOT NULL AND usage_unit IS NOT NULL));

ALTER TABLE cost_records ADD CONSTRAINT ck_cost_usage_nonnegative CHECK (usage_quantity IS NULL OR usage_quantity >= 0);

CREATE INDEX ix_cost_org_currency_period ON cost_records (organization_id, currency, period, department);

UPDATE alembic_version SET version_num='0018' WHERE alembic_version.version_num = '0017';

COMMIT;

