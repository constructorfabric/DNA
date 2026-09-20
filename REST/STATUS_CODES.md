### HTTP status codes and application error codes

This document outlines the usage of HTTP status codes and application-level error codes according to the API Guidelines. Ensure that responses remain consistent across all endpoints.

### Application Error Codes

Every RFC 9457 Problem Details response body carries a **REQUIRED** top-level `code`
member, in addition to the standard `type`/`title`/`status`/`detail`/`instance` members.
This document is the registry for those codes: every application error code used anywhere
in the API MUST appear here exactly once.

- Codes are `SCREAMING_SNAKE_CASE` and stable across versions — `code` is a wire contract
  (PLID-31.03).
- `type` and `code` are 1:1: each `code` has exactly one `type` URI, and each `type`
  resolves back to exactly one `code`.
- `type` URI template: `https://api.example.com/errors/{code-in-kebab-case}`, e.g.
  `INVALID_CURSOR` → `https://api.example.com/errors/invalid-cursor`.

### Success

- 200 OK: Standard successful GET/PUT/PATCH responses.
- 201 Created: Resource successfully created. Include `Location` header.
- 202 Accepted: Async operation accepted; returns operation status handle.
- 204 No Content: Successful mutation with no body.
- 207 Multi-Status: Batch/bulk request with mixed per-item outcomes. Originates in
  RFC 4918 (WebDAV) and is reused here for JSON batch envelopes; see `BATCH.md`.
- 304 Not Modified: Conditional `GET`/`HEAD` with `If-None-Match` matches the current
  representation; no body returned.

Out of scope (deliberately not covered by this document): 1xx informational responses,
and 3xx redirection status codes other than `304`.

### Client errors

#### 400 vs 422 Decision Rule

- **400** — the request is unparseable, or it names an identifier outside the endpoint's
  allowlist.
- **422** — the request parses and names valid fields, but a value violates a documented
  constraint.

**Carve-out:** `ORDER_MISMATCH`, `FILTER_MISMATCH` and `FIELD_SELECTION_MISMATCH` stay
**400** even though the rule above would suggest 422. The fault is in how the request was
assembled — `$orderby`/`$filter`/`$select` contradicts a cursor token the request itself
carries — not in a field value, so it is treated as a malformed request rather than a
value-level validation failure.

- 400 Bad Request
  - Malformed syntax, invalid parameters, or invalid cursor.
  - Error codes:
    - Pagination: `INVALID_CURSOR`, `ORDER_MISMATCH`, `FILTER_MISMATCH`, `UNSUPPORTED_FILTER_FIELD`, `UNSUPPORTED_ORDERBY_FIELD`
    - Field projection: `INVALID_FIELD`, `FIELD_SELECTION_MISMATCH`
    - Idempotency: `INVALID_IDEMPOTENCY_KEY`
    - Batch: `BATCH_CONFLICT` (cross-item conflict detected before execution; see `BATCH.md`)
    - General: `INVALID_QUERY`
- 401 Unauthorized
  - Missing/invalid/expired auth.
  - Error codes: `UNAUTHENTICATED`, `TOKEN_EXPIRED`.
- 403 Forbidden
  - Authenticated but not authorized.
  - Error codes: `FORBIDDEN`, `INSUFFICIENT_PERMISSIONS`.
- 404 Not Found
  - Resource or route not found.
  - Error codes: `NOT_FOUND`.
- 405 Method Not Allowed
  - HTTP method not supported for this resource. Include `Allow` header.
  - Error codes: `METHOD_NOT_ALLOWED`.
- 406 Not Acceptable
  - The requested `Accept` media type is not supported.
  - Error codes: `NOT_ACCEPTABLE`.
- 408 Request Timeout
  - Client took too long to send the complete request.
  - Error codes: `REQUEST_TIMEOUT`.
- 409 Conflict
  - Resource state conflict (duplicate, version conflict, invariant violation).
  - Error codes: `CONFLICT`, `VERSION_CONFLICT`, `DUPLICATE`, `IDEMPOTENCY_IN_PROGRESS`.
  - `IDEMPOTENCY_IN_PROGRESS` (the first request for a given `Idempotency-Key` is still
    in flight) MUST include a `Retry-After` header.
- 410 Gone
  - Resource permanently deleted or endpoint permanently removed (retired).
  - Error codes: `GONE`, `PERMANENTLY_DELETED`, `ENDPOINT_RETIRED`.
  - Use for: Hard-deleted resources, retired API versions after their sunset date.
  - A deprecated but not yet retired endpoint MUST NOT return `410`; it returns its
    normal status codes plus `Deprecation` and `Sunset` headers (see `VERSIONING.md`).
- 412 Precondition Failed
  - ETag preconditions failed.
  - Error codes: `PRECONDITION_FAILED`.
- 413 Payload Too Large / 414 URI Too Long
  - Request exceeds limits (body or URL length).
  - Error codes: `REQUEST_TOO_LARGE`, `URI_TOO_LONG`.
- 415 Unsupported Media Type
  - Content-Type not supported.
  - Error codes: `UNSUPPORTED_MEDIA_TYPE`.
- 422 Unprocessable Entity
  - Validation failed, semantically invalid input.
  - Error codes: `INVALID_LIMIT`, `VALIDATION_ERROR`, `SCHEMA_MISMATCH`, `TOO_MANY_FIELDS`,
    `BATCH_FAILED` (atomic batch rolled back; see `BATCH.md`),
    `IDEMPOTENCY_KEY_REUSED`.
  - `IDEMPOTENCY_KEY_REUSED` is returned when the same `Idempotency-Key` is reused with a
    different request fingerprint (method, path, and canonical body hash).
- 428 Precondition Required
  - The request is required to be conditional or include a specific precondition (e.g., `If-Match`, `Idempotency-Key`) per API policy.
  - Error codes: `PRECONDITION_REQUIRED`.
- 429 Too Many Requests
  - Rate limit exceeded; include standard rate limit headers.
  - Error codes: `RATE_LIMITED`.
- 431 Request Header Fields Too Large
  - Request header fields are too large. Reduce header sizes (e.g., cookies) and retry.
  - Error codes: `HEADERS_TOO_LARGE`.
- 451 Unavailable For Legal Reasons
  - Access blocked due to legal requirements (GDPR, content filtering, geo-restrictions, court orders).
  - Error codes: `LEGAL_BLOCK`, `GEO_RESTRICTED`, `CONTENT_BLOCKED`.

### Server errors

- 500 Internal Server Error
  - Unexpected server-side error. **Never expose internal details** (stack traces, database errors) to clients.
  - Error codes: `INTERNAL_ERROR`.
  - Use for: Unhandled exceptions, unexpected state, programming errors.
- 502 Bad Gateway
  - Upstream service returned invalid HTTP response (malformed headers, protocol errors, invalid status line), connection refused, or closed connection unexpectedly.
  - Error codes: `UPSTREAM_ERROR`, `INVALID_UPSTREAM_RESPONSE`, `UPSTREAM_PROTOCOL_ERROR`.
  - Use for: Returned by API gateways, reverse proxies, load balancers, or BFF services when upstream is at fault. Application servers should not return 502 for their own errors.
- 503 Service Unavailable
  - Service temporarily overloaded, under maintenance, or degraded. Include `Retry-After` header when possible.
  - Error codes: `SERVICE_UNAVAILABLE`, `MAINTENANCE_MODE`, `OVERLOADED`.
  - Use for: Planned maintenance, circuit breaker open, resource exhaustion, database unreachable, critical service dependency unavailable.
- 504 Gateway Timeout
  - Upstream service did not respond within the configured timeout period (no response received, connection timeout, read timeout).
  - Error codes: `UPSTREAM_TIMEOUT`, `GATEWAY_TIMEOUT`.
  - Use for: Returned by API gateways, reverse proxies, load balancers, or BFF services when waiting for upstream. Application servers should not return 504 for their own slow operations.

**5xx vs 4xx Decision**:
- Use **4xx** when the client can fix the problem (bad input, missing auth, etc.)
- Use **5xx** when the server/infrastructure has the problem (bugs, outages, dependencies)
- When in doubt: if retrying the identical request might succeed after server recovery, use 5xx

### Applicability by HTTP method

These are typical status codes for each HTTP method. Edge cases may warrant additional codes not listed here.

- **GET**
  - Success: `200` (OK), `304` (Not Modified)
  - Client errors: `400`, `401`, `403`, `404`, `406`, `408`, `410`, `429`, `431`, `451`
- **POST**
  - Success: `201` (created), `202` (async), `200` (idempotent replay)
  - Client errors: `400`, `401`, `403`, `404`, `405`, `406`, `408`, `409`, `410`, `415`, `422`, `428`, `429`, `431`, `451`
- **PUT**
  - Success: `200` (replaced), `204` (no body), `201` (upsert if supported)
  - Client errors: `400`, `401`, `403`, `404`, `405`, `406`, `408`, `409`, `410`, `412`, `415`, `422`, `428`, `429`, `431`, `451`
- **PATCH**
  - Success: `200` (updated), `204` (no body)
  - Client errors: `400`, `401`, `403`, `404`, `405`, `406`, `408`, `409`, `410`, `412`, `415`, `422`, `428`, `429`, `431`, `451`
- **DELETE**
  - Success: `204` (deleted), `202` (async delete), `200` (soft-delete payload)
  - Client errors: `400`, `401`, `403`, `404`, `405`, `406`, `408`, `409`, `410`, `412`, `428`, `429`, `431`, `451`
- **OPTIONS**
  - Success: `200` (OK), `204` (No Content)
  - Client errors: `401`, `403`, `429`
- **HEAD**
  - Success: `200` (OK), `304` (Not Modified)
  - Client errors: Same as GET (without body)

### Retry Guidance for Clients

Understanding which status codes are safe to retry is critical for building resilient clients without causing duplicate operations or data corruption. Retry eligibility follows a method's **safety**, not merely its idempotency: retrying a safe method never has side effects, while retrying an idempotent-but-unsafe method can still race with itself. Per RFC 9110 §9.2.2, the idempotent set (`GET`, `HEAD`, `OPTIONS`, `PUT`, `DELETE`) is a superset of the safe set (`GET`, `HEAD`, `OPTIONS`).

**Tier 1 — Safe (`GET`, `HEAD`, `OPTIONS`): retry freely.**

The following status codes are **safe to retry automatically** for these methods:

- `408` Request Timeout
- `429` Too Many Requests (respect `Retry-After` header)
- `500` Internal Server Error
- `502` Bad Gateway
- `503` Service Unavailable (respect `Retry-After` header)
- `504` Gateway Timeout

**Tier 2 — Idempotent but not safe (`PUT`, `DELETE`): retry unless the endpoint documents side effects.**

- `PUT` is idempotent when replacing a complete resource (same request = same result).
- `DELETE` is typically idempotent (deleting an already-deleted resource still results in "not found").
- However, implementation details matter: if `PUT` performs side effects (e.g., incrementing counters) or `DELETE` has non-idempotent behavior, treat them as non-idempotent and require `Idempotency-Key` for safe retries.
- Check your API documentation to determine whether a specific endpoint is truly idempotent before retrying the Tier 1 status codes above for `PUT`/`DELETE`.

**Tier 3 — Neither safe nor idempotent (`POST`, `PATCH`): retry only with `Idempotency-Key`.**

- **Only retry if** the request includes an `Idempotency-Key` header.
- Without `Idempotency-Key`, retrying may cause duplicate operations (double charges, duplicate resources, etc.).

**Retry Strategy Best Practices:**

- Use **exponential backoff** with jitter to avoid thundering herd
- Respect `Retry-After` header when present (`429`, `503`)
- Set a **maximum retry limit** (e.g., 3-5 attempts)
