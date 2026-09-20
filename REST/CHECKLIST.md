# Conformance Checklist

"Is this API DNA-compliant?" should not require reading 2,000 lines of guideline. This is a
review checklist in the shape of PLID's "Minimal Review/Approval Checklist": one line per
checkable norm, grouped by [API.md](API.md) section.

Every line is tagged:

- **[machine: `<rule-name>`]** — enforced by [`schemas/spectral.yaml`](../schemas/spectral.yaml).
  The rule name corresponds exactly to a rule in that file; if the two ever disagree, the
  ruleset is the bug.
- **[human-reviewed]** — no generic OpenAPI lint rule can decide this; a reviewer checks it
  against the endpoint's own documentation.

A ruleset rule at `severity: warn` does not exist in this corpus — every machine-checked line
below is enforced at `severity: error` in `spectral.yaml`, because a warning is a rule that will
never actually block a merge.

## §3 Resource Modeling & URLs

- Identifiers are lowercase hyphenated UUIDv7, never a type-prefixed or ULID-on-the-wire form. **[human-reviewed]**
- Response timestamps are UTC, `Z`-suffixed, exactly three fractional digits. **[machine: `dna-timestamp-millis-example`]**

## §4 JSON Conventions

- JSON property names are snake_case. **[machine: `dna-snake-case-properties`]**
- List responses use the `items` + `page_info` envelope; single objects are unwrapped. **[machine: `dna-list-envelope-shape`]**
- Absent fields are omitted rather than sent as `null`, except the Merge Patch delete sentinel (§6). **[human-reviewed]**

## §5 Pagination, Filtering, Sorting, Field Projection

- `limit` default/min/max come from [CONSTANTS.md](CONSTANTS.md); out-of-range `limit` is rejected, never clamped. **[human-reviewed]**
- Every collection `GET` that accepts `$filter`/`$orderby` publishes its allowlist via `x-odata-filter`/`x-odata-orderby`. **[machine: `dna-collection-get-has-query-allowlists`]**
- Cursors are opaque to clients; nothing in the endpoint's own documentation instructs clients to decode or construct one. **[human-reviewed]**
- `page_info` does not carry `total_count`. **[machine: `dna-no-total-count-in-page-info`]**
- `$select` field count and allowlist are enforced per [CONSTANTS.md](CONSTANTS.md) and QUERYING.md. **[human-reviewed]**

## §6 Request Semantics

- `PATCH` uses JSON Merge Patch and documents `null` as the delete sentinel. **[human-reviewed]**
- `POST` returns `201` with `Location` and the created resource in the body. **[human-reviewed]**

## §7 Error Model (Problem Details)

- Every 4xx/5xx response is `application/problem+json` (batch envelope exception aside). **[machine: `dna-problem-json-on-error-responses`]**
- Every Problem Details schema requires the top-level `code` member. **[machine: `dna-problem-requires-code`]**
- `code` values used by the endpoint all appear in [STATUS_CODES.md](STATUS_CODES.md) exactly once. **[human-reviewed]**
- `type` and `code` are 1:1 and `type` follows the kebab-case template. **[human-reviewed]**

## §8 Concurrency & Idempotency

- Mutable representations carry `ETag`; `PATCH`/`PUT` accept `If-Match` and return `412` on mismatch. **[human-reviewed]**
- `Idempotency-Key` is honoured on `POST`/`PATCH`/`DELETE`; malformed keys return `400 INVALID_IDEMPOTENCY_KEY`. **[human-reviewed]**
- A reused key with a different request fingerprint returns `422 IDEMPOTENCY_KEY_REUSED`. **[human-reviewed]**
- A reused key for a still-in-flight request returns `409 IDEMPOTENCY_IN_PROGRESS` with `Retry-After`. **[human-reviewed]**
- Idempotency retention tier (minimum/important/critical) is documented per endpoint per [CONSTANTS.md](CONSTANTS.md). **[human-reviewed]**

## §9 Authentication & Authorization

- Every `401` response carries a `WWW-Authenticate: Bearer …` challenge in RFC 6750 form. **[human-reviewed]**
- Required scopes are documented per endpoint using the `<resource>:<action>` convention. **[human-reviewed]**
- The endpoint states whether it returns `403` or `404` for a resource the caller may not know exists (AUTH.md 403-vs-404). **[human-reviewed]**

## §10 Rate Limiting & Quotas

- Successful and `429` responses carry `RateLimit` and `RateLimit-Policy`. **[machine: `dna-operational-headers-present`]**
- `429` responses include `Retry-After`. **[human-reviewed]**

## §11 Asynchronous Operations

- The job resource's `error` member is a Problem Details object, not an untyped map. **[human-reviewed]**
- Non-terminal job responses include `Retry-After`. **[human-reviewed]**
- `DELETE /jobs/{id}` either cancels the job or documents `405`. **[human-reviewed]**
- Jobs expose `expires_at`; an expired job returns `410 Gone`, not `404`. **[human-reviewed]**

## §12 Webhooks (Outbound)

- `X-Signature`/`X-Timestamp` are present and the signature base string matches [WEBHOOKS.md](WEBHOOKS.md) exactly. **[human-reviewed]**
- The event payload uses `event_type` and `id`, matching `X-Event-Id` on the wire. **[human-reviewed]**
- Receivers are documented as tolerant of out-of-order delivery. **[human-reviewed]**

## §13 Internationalization, Numbers & Time

- Response timestamps carry `.SSS` precision; request/`$filter` timestamp inputs accept any RFC 3339 form. **[machine: `dna-timestamp-millis-example`]**

## §14 Caching

- Cacheable reads carry `ETag`; conditional `GET` with `If-None-Match` returns `304`. **[human-reviewed]**

## §15 Security & CORS

- Every header a browser client is expected to read appears in `Access-Control-Expose-Headers`. **[human-reviewed]**

## §16 Observability & Diagnostics

- `X-Trace-Id` is present on every response; `trace_id` is used only as the JSON member and log field, never as a header name. **[machine: `dna-operational-headers-present`]**

## §17 Versioning & Deprecation

- Deprecated-but-not-retired endpoints return normal status codes plus `Deprecation` (RFC 9745, `@<unix-seconds>`, never `true`) and `Sunset`. **[human-reviewed]**
- `410 Gone` is used only for retired endpoints. **[human-reviewed]**

## §19 Batch & Bulk

- One batch endpoint implements exactly one operation; `id` presence in an item never changes it. **[human-reviewed]**
- Batch envelope responses (`200`/`207`/all-failed aggregate) are `application/json` with per-item Problem Details `error` objects; only a batch-level failure with no envelope is `application/problem+json`. **[human-reviewed]**

## §20 OpenAPI & Codegen

- The document `$ref`s `schemas/components.openapi.yaml` (`PageInfo`, `Problem`, `ValidationError`, the five query parameters) instead of retyping them. **[human-reviewed]**
- The document validates against `schemas/spectral.yaml` at `--fail-severity warn`. **[human-reviewed]**

## §24 Documentation Style

- Every documented example satisfies this guideline: UUIDv7 identifiers, `.SSS` timestamps, `code` on every error body. **[human-reviewed]**

## §25 Uploads

- The endpoint states its own binary size limit; it does not inherit the 1 MB JSON cap. **[human-reviewed]**
- Content type is sniffed and checked against an allow-list, never a deny-list. **[human-reviewed]**
- Download URLs are short-lived and pre-signed. **[human-reviewed]**
