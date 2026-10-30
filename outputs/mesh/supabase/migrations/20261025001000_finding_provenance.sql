BEGIN;

-- Running upgrade 0021 -> 0022

ALTER TABLE scan_jobs ADD CONSTRAINT uq_scan_finding_provenance UNIQUE (organization_id, repository_id, id, commit_sha);

ALTER TABLE findings ADD COLUMN "column" INTEGER;

ALTER TABLE findings ADD COLUMN dependency JSON;

ALTER TABLE findings ADD COLUMN scan_job_id VARCHAR(36);

ALTER TABLE findings ADD COLUMN commit_sha VARCHAR(40);

ALTER TABLE findings ADD CONSTRAINT fk_finding_scan_commit FOREIGN KEY(organization_id, repository_id, scan_job_id, commit_sha) REFERENCES scan_jobs (organization_id, repository_id, id, commit_sha);

ALTER TABLE findings ADD CONSTRAINT ck_finding_provenance_pair CHECK ((scan_job_id IS NULL AND commit_sha IS NULL) OR (scan_job_id IS NOT NULL AND commit_sha IS NOT NULL));

ALTER TABLE findings ADD CONSTRAINT ck_finding_commit_length CHECK (commit_sha IS NULL OR length(commit_sha)=40);

ALTER TABLE findings ADD CONSTRAINT ck_finding_column_positive CHECK ("column" IS NULL OR "column">0);

CREATE INDEX ix_finding_org_repository_scan ON findings (organization_id, repository_id, scan_job_id);

UPDATE alembic_version SET version_num='0022' WHERE alembic_version.version_num = '0021';

COMMIT;

