# Worker liveness and cycle checks

Outbox/provisioning dispatch, cloud assessment, scan, OCR and retention CLI loops now publish private local heartbeat records. A monitor thread refreshes every five seconds while the main loop works or sleeps. Records contain only worker kind, tenant UUID, random process-instance UUID, timestamps, state, completed-cycle count and a fixed error code; no payloads, credentials, provider errors, hostnames or raw exception text are stored.

Files live in a private per-user temporary directory and use atomic replacement with owner-only permissions where supported. Names bind the worker kind and canonical tenant UUID. The default is one worker of each kind/tenant per filesystem namespace; Compose isolates service `/tmp` mounts. This is a local process monitor, not a multi-instance registry, ownership lease, API authentication mechanism or cluster discovery service.

```sh
python -m app.worker_health --kind outbox --organization TENANT_UUID
```

The checker returns sanitized JSON and exit 0 only for an acceptable running/idle observation. Missing, malformed, foreign, stale, stopped/error or overdue records return exit 1. Heartbeats older than 30 seconds or more than five seconds in the future fail. A fresh heartbeat cannot hide an overdue main cycle or idle loop:

| Kind | Maximum active cycle | Maximum idle interval since completion |
|---|---|---|
| outbox | 30 minutes | 15 seconds |
| cloud | 5 minutes | 30 seconds |
| scan | 40 minutes | 30 seconds |
| ocr | 10 minutes | 30 seconds |
| retention | 15 minutes | 150 seconds |

These are conservative process-monitor thresholds, not provider timeouts or service-level guarantees. A completed cycle can include handled retries/dead letters or an empty queue; it is not a completed job or confirmed external action. Existing lease/fencing, authorization, retry and transaction logic remains authoritative. Busy scan/cloud/OCR queues still drain immediately, with the same idle backoff; outbox and retention keep their existing intervals.

Normal one-shot completion publishes `stopped`; a long-running health probe should then fail. Unhandled loop failures publish a fixed failure state, log structured worker-kind/exception-class metadata and exit 1 without a raw traceback. Keyboard interruption exits 130. Failure to write monitoring data does not skip business work, but health is unavailable and checks fail. A crashed process can remain apparently live until the short heartbeat freshness window expires. Files are temporary, not durable job history.

Compose outbox, cloud and retention services run healthchecks every ten seconds with five-second timeouts and a 15-second startup grace. Docker's unhealthy state does not automatically abort or replay jobs. Configure production alerting/restart policy separately after evaluating legitimate workload durations. Scanner/OCR host-worker deployments can use the same CLI with `--kind scan` or `--kind ocr`; those worker services are not launched by the generic Compose acceptance driver.

Focused tests cover lifecycle states, live background refresh, main-cycle deadlines, clock/stale checks, malformed/foreign records, tenant path binding, permissions, write failures, redacted failures, backoff preservation and actual cross-process CLI observation. `worker-health-live-results.json` records real outbox/cloud/retention process and Docker-health checks over a disposable empty-queue tenant. This does not establish external integration success, throughput, alert delivery or production worker supervision.

The native committed outbox/Mailpit verifier also passes after the loop changes: an actual child worker delivers the synthetic invitation, records its receipt, avoids duplicating that committed receipt on replay, and removes the uniquely marked hosted fixtures. This is local SMTP evidence, not an external inbox delivery test.

The Compose acceptance driver copies only exact required offline-wheel versions and removes only its generated project image aliases after its containers/volumes/networks are down. It preserves the current application image and unrelated tags; shared untagged build caches are not globally pruned. Twelve regression cases cover cleanup-name boundaries and wheel-cache selection.
