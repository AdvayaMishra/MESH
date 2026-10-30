BEGIN;

-- Running upgrade 0028 -> 0029. Existing policies and table grants are unchanged.
CREATE INDEX ix_memberships_user_org ON memberships (user_id, organization_id);

CREATE POLICY self_membership_discovery ON memberships FOR SELECT
    USING (
        nullif(current_setting('mesh.organization_id', true), '') IS NULL
        AND user_id = nullif(current_setting('mesh.user_id', true), '')
        AND active
    );

UPDATE alembic_version SET version_num='0029' WHERE version_num='0028';

COMMIT;
