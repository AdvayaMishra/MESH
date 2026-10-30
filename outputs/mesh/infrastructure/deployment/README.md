# Backend deployment preparation

This standalone Compose scaffold uses externally managed PostgreSQL/Redis and a separately selected HTTPS ingress. It does not create a server, domain, subscription or provider account. Source configuration was resolved with the real Compose CLI using isolated synthetic values; no production service was started. The development `docker-compose.yml` remains separate.

Keep actual settings in a protected file outside source/archive outputs. `.env.production.example` deliberately contains empty required values. The deployed image must be built from the reviewed current source and supplied as `MESH_BACKEND_IMAGE=repository@sha256:...`; this scaffold does not build or publish images. Existing hosted migration0028 and earlier remain frozen; apply any future approved migration with separate administrator authority before starting the restricted runtime.

The API listens on host loopback8000 behind the selected TLS ingress. Set `MESH_PUBLIC_URL`, exact HTTPS `CORS_ORIGINS`, an invitation endpoint on that application origin and the exact `MESH_TRUSTED_PROXY_IPS` observed from the ingress. Wildcard proxy trust is not accepted by the configuration gate. The scaffold enforces production mode, disables test mode, enables privileged MFA and requires authenticated STARTTLS mail. Runtime settings additionally reject unauthenticated/plaintext Redis or disabled Redis certificate/hostname verification. For example, the Redis URL scheme must be `rediss`; URL credentials must be encoded correctly.

All five service definitions use UID10001, a read-only root filesystem, bounded tmpfs, dropped capabilities, no privilege escalation, PID/CPU/memory bounds, restart policy and health checks. Workers publish no ports. No host directory or Docker socket is mounted into these services. Runtime secrets are injected only into the backend services, not the frontend or image layers. The Supabase management PAT is not a runtime input.

Profiles `worker`, `documents`, `cloud` and `billing` are opt-in. Supply a real authorized `WORKER_ORGANIZATION_ID` before launching a tenant worker. The all-zero fallback cannot resolve to a tenant and causes the worker to fail closed; it is not a synthetic production organization. Each additional tenant needs its own explicitly configured worker deployment. Cloud/billing remain optional and do not require obtaining an AWS account just to run MESH.

OCR/scanner inference needs a separately trusted worker host with the dedicated Linux Docker launcher and reviewed images. This backend image does not include a Docker daemon/CLI or receive its socket. `DOCUMENT_OCR_ENABLED` remains false until the document pipeline is accepted. For remote malware screening use `CLAMAV_TLS=true`, a certificate-valid endpoint and optional absolute `CLAMAV_CA_FILE`/`CLAMAV_TLS_SERVER_NAME`. A custom CA must be provisioned read-only at that path; the default manifest uses system trust and has no arbitrary host mounts. Native clamd TCP is not TLS: use an appropriately configured TLS termination service in front of it. Runtime production validation permits plaintext only to an explicit loopback endpoint, for a local trusted process/sidecar.

From the backend root, these commands perform preparation checks only:

```text
python scripts/verify_production_configuration.py --env-file <protected-production-file> --require-directory --require-ocr --ocr-assessment <matching-current-image-assessment.json> --output <redacted-readiness.json>
python scripts/verify_production_compose.py --docker-executable <absolute-docker-path> --output <manifest-validation.json>
docker compose --env-file <protected-production-file> -f infrastructure/deployment/compose.yml config --quiet
```

Use `--compose-executable <absolute-standalone-compose-path>` instead of `--docker-executable` where appropriate. The configuration checker does not inherit missing values from the operator's environment. It reports field/check identifiers rather than credentials, refuses to overwrite its input and never grants release/privacy approval. With `--require-ocr`, the image assessment must match the configured image, be complete/clean and be no more than24hours old (timezone required; at most5minutes of future clock tolerance). A failed historical image scan cannot be replaced with an invented passing report.

Before actual activation, verify DNS/certificates, ingress source-IP forwarding, provider Auth policy, verified-TLS restricted database role, authenticated Redis, actual privileged-account MFA, per-tenant worker authority, dependency availability and recovery/monitoring procedures on the chosen host. Current local manifest/configuration evidence is not a claim that those external deployment checks succeeded. Pending operator actions are recorded in `docs/workstreams/R1_DEFERRED_OPERATOR_ACTIONS.md`.
