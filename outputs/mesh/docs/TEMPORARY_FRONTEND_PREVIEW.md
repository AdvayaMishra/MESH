# MESH temporary frontend integration — 27 October 2026

The supplied checkpoint ZIP is unchanged. The working copy is `outputs/mesh-preview-frontend`; it is separate from the canonical backend and the final frontend expected later. This checkpoint restores the original sidebar, topbar, cards, directory and project/task screens around authenticated backend data. The previous generic request/JSON workspace is no longer the connected dashboard.

## Current runtime and evidence boundary

The latest native-screen production build/TypeScript and focused lint pass. All15 local browser integration cases passed, including reload persistence, tenant/role denials, complaints and synthetic risk workflows; final process cleanup succeeded and real-account rerun results are recorded in `docs/native-preview-checkpoint.json`. The unchanged original demo passed70 role/navigation cases. Full frontend lint reports zero errors/five inherited warnings. Backend verification remains1,067 passed /32 skipped, Ruff, mypy95 and Bandit passed. No migration:0028/57 forced-RLS application tables; OpenAPI188 operations/162 paths.

The real preview runs at http://127.0.0.1:3000/login with the actual backend on8000. Real Redis7.4.11 runs as nobody inside a snapshot of the approved disposable VM, with an ephemeral password, protected mode and host loopback forwarding. The backend passed both health checks. The final native-build rerun passed five real Supabase browser journeys and12 backend read/authorization checks. Its outcome is recorded separately from substituted-identity tests.

## Connected screens and actions

- Sign-in/registration/current profile: server-side token cookies and backend membership authority. Friendly names and application-role labels replace raw profile JSON. Registration captures owner name; company creation is a separate action. Existing-organization selection uses a real organization reference.
- Projects and tasks: real list, project proposal, independent senior review, owner decision, project comments, task creation and task status updates. Mutation errors stay visible, and reloads read backend state. Task creation currently requires the assignee's user reference because the authorized developer API does not expose a complete membership picker.
- HR: actual employee directory/detail with tenant-scoped email/role metadata; recorded payroll and leave, leave decisions, lifecycle proposal/review/execution, private identity-document upload/review and explicitly untrusted OCR suggestions. Payroll records are manual approved amounts, not automatic tax processing.
- Complaints: user submissions and own-case view; HR can see permitted cases and advance other users' cases from open to investigating to resolved. This is identified, confidential reporting, not anonymous reporting. The list currently loads at most 100 cases.
- Finance: actual cost/budget records, manual entry and backend proportional what-if calculations. No fabricated forecasts or past-period comparisons.
- Security: actual events/anomalies, incident list/detail, notes, recorded transitions and graph evidence; saved cloud assessments/job reads; scoped AI insights; owner-only repository registration (Organization), repository lookup, scan request/status polling, saved finding review/history, risk assessments and labelled synthetic simulation. A queued scan is not a completed scanner run. Synthetic evidence remains labelled.
- Workspace: actual audit records, current session list/revoke-others, MFA controls, domain proof and invitation management, authorized Trust Stars lookup and scoped owner/HR/security insights. Complaints, Trust Stars and Insights now have sidebar links. Initial audit loading is limited to100 records and labelled when capped. Initial data reads share requests and run at most four concurrently.

All data is scoped to the selected membership. Failed tenant selection clears the preceding data. Backend authorization remains decisive. Finance, HR, developer and analyst routes follow actual backend permissions; role switching exists only in the separately labelled demo.

## Explicitly unfinished mappings

The preview now includes organization DNS-and-website proof, invitation creation/resend/revocation, Supabase authenticator enrollment/challenge/verification/removal, repository registration and finding disposition/history, synthetic simulation, saved risk assessments with uncertainty and default owner risk-policy creation. Local browser acceptance covers the core workflows and visibility/permissions of the added controls. Provider-specific execution still requires its actual configuration and permissions. Custom risk-policy editing, invitation acceptance from emailed links, a project membership picker, streaming and exceptional document/lifecycle reconciliation transitions remain outside the temporary native preview; their backend contracts remain available. Email verification/recovery/password forms exist; the CAPTCHA widget/site key and actual inbox acceptance remain configuration work.

Notification delivery/read state, arbitrary reports, profile editing and pull-request/merge controls lack the required backend contracts. These routes show a clear explanation. Missing time series, story points, priorities, repository health, asset counts, risk improvements and employee compensation are not synthesized. A complete team membership or monitoring coverage claim is not inferred from a paginated task/event list. Core lists have a 2,000-record ceiling with a warning; the initial audit view is capped at100; specialist lists commonly load only the stated first page.

AWS remains deferred. Scanner, malware/OCR, mail, SCIM and AI providers/workers require their real configuration. No worker completion, provider activation, email delivery, production MFA enforcement or complete cloud coverage is established by a browser view.

## Hosted fixture and credential boundary

The approved setup created five confirmed fictional Auth identities, two isolated organizations, memberships and five employee records. Their domains remain unverified and document verification pending. The protected private ledger stays outside deliverables. Never print it, put secrets into NEXT_PUBLIC variables, export authenticated browser traces/cookies or rerun fixture creation.

Automatic approval review rejected optional hosted business seeding; no hosted project, cost, budget, payroll, leave, complaint or incident seeding was performed. Browser write tests use an isolated SQLite database with substituted provider identity and an explicit sandbox banner. These tests exercise real backend routers, not real Supabase identity or PostgreSQL/RLS.

The dedicated real-account convenience helper remains server-only, opt-in, exact-origin/loopback restricted, limited to the five approved identities and time-bounded by its ledger expiry. An expired helper must not be silently extended. Its cookies are HttpOnly/SameSite Strict and chunked as required. Normal sign-in/session access records and audits are retained. Retirement requires an authorized owned-fixture cleanup; append-only history must remain intact.

## Running and verification

Use the bundled Node runtime recorded in the workspace validation runner. The temporary preview uses `.next-native`, worker threads and request rendering to avoid Windows build-worker/file-permission failures. The original ZIP/final frontend is unaffected. The build is `next build`; start only on `127.0.0.1:3000` after the actual backend and real Redis have passed readiness. Never switch on substituted authentication to make real-account mode appear healthy.

`work/run_mesh_preview_services.py` owns only its loopback children and has a 12-hour bound. The optional `work/run_mesh_preview_redis_vm.py` uses a QEMU snapshot of the approved disposable disk, unprivileged guest Redis and only a loopback host forward. It does not modify the original disk or prove pinned Compose-image provenance. An external-Redis launch requires actual PING and the owned VM readiness marker. Scoped sleep-prevention requests are restored when their runners exit; permanent Windows power settings are unchanged.

Local Playwright servers are bounded and use separate sandbox cookies/database. Original demo tests use `/demo-login` and never establish backend authority. Runtime logs/evidence distinguish current checks, historical checks and checks not run. Current code has not been uploaded to GitHub and no new backend ZIP has been created.


Current local launcher: run `work/venv/Scripts/python.exe work/run_mesh_preview_redis_vm.py`, wait for actual Redis PING and backend readiness, then run `work/venv/Scripts/python.exe work/run_mesh_native_frontend.py`. The VM runner privately supplies its temporary Redis password to its owned backend launcher; do not launch a second backend manually. Both launchers are bounded to12hours. Stop only owned services through their scoped stop markers.


Current acceptance boundary: native authentication, role/tenant separation, proposal persistence, complaints and synthetic-risk flows are exercised locally; real approved-account checks are read-only. No live MFA enrollment, DNS/domain proof, invitation email, GitHub registration/scanner execution, production policy mutation or additional hosted business seeding is performed by automated preview acceptance. Native controls make the configured APIs usable; they do not fabricate provider success.
