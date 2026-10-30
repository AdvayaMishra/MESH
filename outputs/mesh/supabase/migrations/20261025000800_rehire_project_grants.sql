BEGIN;

-- Running upgrade 0019 -> 0020

CREATE FUNCTION public.mesh_rehire_clear_project_grants(reviewed_plan text)
    RETURNS integer LANGUAGE plpgsql SECURITY DEFINER
    SET search_path = pg_catalog
    AS $mesh_rehire$
    DECLARE
        scoped_org text := nullif(current_setting('mesh.organization_id', true), '');
        scoped_user text := nullif(current_setting('mesh.user_id', true), '');
        target_user text;
        removed integer;
    BEGIN
        IF scoped_org IS NULL OR scoped_user IS NULL OR NOT EXISTS (
            SELECT 1 FROM public.memberships m JOIN public.organizations o ON o.id=m.organization_id
            WHERE m.organization_id=scoped_org AND m.user_id=scoped_user
                AND m.active AND m.role='owner' AND o.status='active'
        ) THEN
            RAISE EXCEPTION 'Active tenant owner required' USING ERRCODE='42501';
        END IF;
        SELECT e.user_id INTO target_user
        FROM public.lifecycle_plans p
        JOIN public.employees e ON e.organization_id=p.organization_id AND e.id=p.employee_id
        JOIN public.memberships m ON m.organization_id=e.organization_id AND m.user_id=e.user_id
        JOIN public.memberships a ON a.organization_id=p.organization_id AND a.user_id=p.approved_by
        WHERE p.id=reviewed_plan AND p.organization_id=scoped_org AND p.kind='rehire'
            AND p.status='reconciliation_required' AND p.proposed_by<>p.approved_by
            AND p.proposed_by<>scoped_user AND a.active AND a.role='owner'
            AND NOT m.active AND m.role NOT IN ('owner','hr')
            AND e.status='offboarded' AND e.verification_status='approved';
        IF target_user IS NULL THEN
            RAISE EXCEPTION 'Independently reviewed inactive rehire required' USING ERRCODE='42501';
        END IF;
        DELETE FROM public.project_members WHERE organization_id=scoped_org AND user_id=target_user;
        GET DIAGNOSTICS removed = ROW_COUNT;
        RETURN removed;
    END
    $mesh_rehire$;
    REVOKE ALL ON FUNCTION public.mesh_rehire_clear_project_grants(text) FROM PUBLIC;
    DO $grant_rehire$ BEGIN
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='mesh_runtime') THEN
            GRANT EXECUTE ON FUNCTION public.mesh_rehire_clear_project_grants(text) TO mesh_runtime;
        END IF;
    END $grant_rehire$;;

UPDATE alembic_version SET version_num='0020' WHERE alembic_version.version_num = '0019';

COMMIT;

