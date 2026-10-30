-- Run as Supabase database administrator, separately from application Alembic migrations.
INSERT INTO storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
VALUES ('mesh-identity', 'mesh-identity', false, 2097152, ARRAY['image/png','image/jpeg'])
ON CONFLICT (id) DO UPDATE SET public=false, file_size_limit=2097152,
allowed_mime_types=ARRAY['image/png','image/jpeg'];

-- Restrictive policies override accidental permissive policies for this bucket.
-- No direct client access: HR authorization happens in the backend before 60-second signing.
-- Replace only MESH-owned policies atomically, so this script is safe to reapply.
DO $mesh_storage_policies$
BEGIN
DROP POLICY IF EXISTS mesh_identity_no_client_read ON storage.objects;
DROP POLICY IF EXISTS mesh_identity_no_client_insert ON storage.objects;
DROP POLICY IF EXISTS mesh_identity_no_client_update ON storage.objects;
DROP POLICY IF EXISTS mesh_identity_no_client_delete ON storage.objects;
CREATE POLICY mesh_identity_no_client_read ON storage.objects AS RESTRICTIVE
FOR SELECT TO anon, authenticated USING (bucket_id <> 'mesh-identity');
CREATE POLICY mesh_identity_no_client_insert ON storage.objects AS RESTRICTIVE
FOR INSERT TO anon, authenticated WITH CHECK (bucket_id <> 'mesh-identity');
CREATE POLICY mesh_identity_no_client_update ON storage.objects AS RESTRICTIVE
FOR UPDATE TO anon, authenticated USING (bucket_id <> 'mesh-identity')
WITH CHECK (bucket_id <> 'mesh-identity');
CREATE POLICY mesh_identity_no_client_delete ON storage.objects AS RESTRICTIVE
FOR DELETE TO anon, authenticated USING (bucket_id <> 'mesh-identity');
END;
$mesh_storage_policies$;
