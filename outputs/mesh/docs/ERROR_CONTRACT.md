# Public API errors

OpenAPI documents MESH's sanitized error envelope for 400, 401, 403, 404, 409, 413, 422, 429, 500 and 503 responses. It does not advertise FastAPI's default rejected-input validation payload. Streaming success contracts remain `text/event-stream`; failures after stream headers use the documented stream error events instead of changing the HTTP status.

```json
{"error":{"code":"validation_error","message":"Request validation failed","fields":["query.limit"],"request_id":"<request-uuid>"}}
```

`fields` contains field locations only and is omitted on other error types. Rejected values, SQL statements/parameters, provider exception text and credentials are excluded. Expected HTTP errors use `http_<status>` codes; middleware uses `rate_limited`, `unavailable` or `request_too_large`; database conflicts use `conflict`; unexpected errors use `internal_error`.

Application error responses include a request ID in the body and `X-Request-ID` header, plus no-store and nosniff headers. Treat request IDs as opaque support identifiers; clients cannot choose them. The schema permits absent/null IDs for failures before request initialization. Reverse proxies and transport failures can have their own response formats.

Preserve `Retry-After` on rate limits and relevant authentication headers. Do not automatically replay non-idempotent mutations or model generation on 409/429/500/503; follow the individual operation's retry contract. Client logs should keep the safe error code/request ID and avoid authentication bodies, signed URLs and private records.

Eight regression cases check every API operation's generated error schema, streaming success preservation, masked validation inputs, early body limits, Redis throttling/outage, database conflicts, unexpected errors and response correlation/security headers.
