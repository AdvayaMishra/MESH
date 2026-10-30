BEGIN;

-- Running upgrade 0020 -> 0021

REVOKE ALL ON FUNCTION public.mesh_retire_telemetry(integer,integer) FROM PUBLIC;
        REVOKE ALL ON FUNCTION public.mesh_rehire_clear_project_grants(text) FROM PUBLIC;
        DO $mesh_function_acl$
        DECLARE api_role text;
        BEGIN
            FOR api_role IN SELECT rolname FROM pg_roles WHERE rolname IN ('anon','authenticated','service_role') LOOP
                EXECUTE 'REVOKE ALL ON FUNCTION public.mesh_retire_telemetry(integer,integer) FROM ' || quote_ident(api_role);
                EXECUTE 'REVOKE ALL ON FUNCTION public.mesh_rehire_clear_project_grants(text) FROM ' || quote_ident(api_role);
            END LOOP;
        END $mesh_function_acl$;;

UPDATE alembic_version SET version_num='0021' WHERE alembic_version.version_num = '0020';

COMMIT;

