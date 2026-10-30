BEGIN;

-- Running upgrade 0014 -> 0015

ALTER TABLE identity_documents ADD COLUMN ocr_status VARCHAR(30) DEFAULT 'not_configured' NOT NULL;

ALTER TABLE identity_documents ADD COLUMN ocr_attempts INTEGER DEFAULT '0' NOT NULL;

ALTER TABLE identity_documents ADD COLUMN ocr_lease_until TIMESTAMP WITH TIME ZONE;

ALTER TABLE identity_documents ADD COLUMN ocr_ciphertext TEXT;

ALTER TABLE identity_documents ADD COLUMN ocr_error_code VARCHAR(60);

ALTER TABLE identity_documents ADD COLUMN ocr_completed_at TIMESTAMP WITH TIME ZONE;

CREATE INDEX ix_identity_ocr_queue ON identity_documents (organization_id, ocr_status, ocr_lease_until);

UPDATE alembic_version SET version_num='0015' WHERE alembic_version.version_num = '0014';

COMMIT;

