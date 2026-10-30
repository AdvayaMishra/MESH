# Vercel + Render deployment preparation

No account login, public deployment, purchase or source publication has been performed by these files.

Vercel project root: outputs/mesh-frontend-completion. Framework: Next.js. vercel.json and .vercelignore are provided. Configure MESH_BACKEND_URL to the exact HTTPS Render origin and NEXT_PUBLIC_TURNSTILE_SITE_KEY to the public widget key before building. Keep every backend credential out of Vercel client settings. Set MESH_LOCAL_SANDBOX=false and keep both CAPTCHA operator-check flags false.

Render Blueprint: root render.yaml creates only a free API web service, with no paid workers or databases. It requires a pre-existing private environment group named mesh-backend-private. Populate it using the existing protected backend settings: restricted verified-TLS Supabase DATABASE_URL with sslrootcert=/srv/mesh/supabase/supabase-ca.crt, public Supabase URL/key, private Storage key, independent AUTH_RATE_SECRET, authenticated rediss:// URL with certificate verification, existing MAIL_ENCRYPTION_KEY, and exact HTTPS Vercel CORS/invitation origin. Never put these values in render.yaml or Git. No migration/reset/bootstrap is run at startup; use the already deployed0029 database. Production MFA is enforced; enroll privileged accounts before relying on production access.

A hosted authenticated TLS Redis endpoint is still required; local loopback Redis cannot be reached from Render. Proxy forwarding remains disabled until actual trusted proxy ranges are established, so spoofable forwarded headers are not trusted. Review rate-limit behavior behind the platform proxy before production acceptance.

Free Render web services block SMTP25/465/587 and sleep after15minutes without traffic. The existing Gmail invitation transport therefore cannot be called fully deployed on this free API alone. No hidden paid worker is created: choose an approved paid mail-worker deployment or implement/configure an authorized HTTPS mail provider separately. Supabase Auth SMTP is sent by Supabase and is a distinct transport. Scanner/OCR/SCIM workers likewise remain explicitly unconfigured rather than simulated.

Deployment sequence: sign into Vercel and Render; select a private source repository or permitted source upload; configure private backend group/TLS Redis; deploy API and verify readiness; configure Vercel backend origin/public CAPTCHA key; deploy frontend; update Supabase Auth site/redirect URLs and Turnstile allowed hostname for the actual assigned Vercel origin; configure invitation URLs; verify genuine Auth/MFA and role/tenant workflows. Preserve localhost entries when needed. Do not invent URLs before the platforms assign them.

Existing public AdvayaMishra/MESH repository was intentionally README-only. No source was pushed there. A deployment-source visibility decision is needed before uploading the code; use a private deployment repository unless explicitly authorized otherwise.

Official references: https://vercel.com/docs/domains/working-with-domains ; https://render.com/docs/blueprint-spec ; https://render.com/docs/free . Configuration is prepared, not live-validated or deployed.
