# REST API Guideline

This document is an actionable, LLM-friendly playbook for building consistent, evolvable REST APIs.

Requirement keywords (`MUST`, `SHOULD`, `MAY`, …) are used as defined in the [Conventions](../README.md#conventions) section of the repository README.

## Table of Contents

### Core Framework

- [1. Core Principles](#1-core-principles)
- [2. Protocol & Content](#2-protocol--content)
- [3. Resource Modeling & URLs](#3-resource-modeling--urls)
- [4. JSON Conventions](#4-json-conventions)
- [5. Pagination, Filtering, Sorting, Field Projection](#5-pagination-filtering-sorting-field-projection)
- [6. Request Semantics](#6-request-semantics)
- [7. Error Model (Problem Details)](#7-error-model-problem-details)

### Advanced Patterns

- [8. Concurrency & Idempotency](#8-concurrency--idempotency)
- [9. Authentication & Authorization](#9-authentication--authorization)
- [10. Rate Limiting & Quotas](#10-rate-limiting--quotas)
- [11. Asynchronous Operations](#11-asynchronous-operations)
- [12. Webhooks (Outbound)](#12-webhooks-outbound)

### Implementation Details

- [13. Internationalization, Numbers & Time](#13-internationalization-numbers--time)
- [14. Caching](#14-caching)
- [15. Security & CORS](#15-security--cors)
- [16. Observability & Diagnostics](#16-observability--diagnostics)
- [17. Versioning & Deprecation](#17-versioning--deprecation)

### Reference

- [18. Canonical Status Codes](#18-canonical-status-codes)
- [19. Batch & Bulk](#19-batch--bulk)
- [20. OpenAPI & Codegen](#20-openapi--codegen)
- [21. Example Endpoints](#21-example-endpoints)
- [22. Backward Compatibility Rules](#22-backward-compatibility-rules-client-facing)
- [23. Performance & DoS](#23-performance--dos)
- [24. Documentation Style](#24-documentation-style)

### Quick Reference

- [Operational Headers](#operational-headers-quick-reference)
- [Constants](#constants)
- [References](#references)

## 1. Core Principles

- **Consistency over novelty**: Prefer one clear way to do things.
- **Explicitness**: Always specify types, units, timezones, and defaults.
- **Evolvability**: Versioned paths, idempotency, and forward-compatible schemas.
- **Observability**: Every request traceable end-to-end.
- **Security first**: HTTPS only, least privilege, safe defaults.

## 2. Protocol & Content

- **Media type**: `application/json; charset=utf-8` (request & response)
- **Errors**: Problem Details `application/problem+json` (RFC 9457) — see [§7](#7-error-model-problem-details)
- **Encoding**: UTF-8
- **Compression**: gzip/br when client sends `Accept-Encoding`
- **Idempotency**: `Idempotency-Key` header on unsafe methods (see [§8](#8-concurrency--idempotency))

## 3. Resource Modeling & URLs

- **Nouns, plural**: `/users`, `/tickets`, `/tickets/{ticket_id}`
- **Hierarchy if strict ownership**: `/users/{user_id}/keys`
- **Prefer top-level + filters** over deep nesting: `/tickets?$filter=assignee_id eq '...'`
- **Identifiers**: resource identifiers MUST be **UUIDv7** (RFC 9562) in lowercase hyphenated
  text form, e.g. `018f6c9e-2c3b-7b1a-8f4a-9c3d2b1a0e5f`. JSON field: `id`.
  - ULID MAY be used as an internal encoding but MUST NOT appear on the wire — cursor
    comparison semantics in [QUERYING.md](QUERYING.md) depend on one canonical text form.
  - Type-prefixed identifiers (`res_01JC…`) MUST NOT be used.
- **Timestamps**: ISO-8601 UTC with `Z`, always including milliseconds `.SSS`
  (e.g., `2025-09-01T20:00:00.000Z`). This governs **response** timestamps; see
  [§13](#13-internationalization-numbers--time) for the scope of the rule.
- **Standard fields**: `created_at`, `updated_at`, optional `deleted_at`

## 4. JSON Conventions

- **Naming**: snake_case (consistent with backend conventions and databases)
- **Nullability**: Prefer omitting absent fields over `null`. The one exception is a JSON
  Merge Patch request body, where `null` is the delete sentinel — see [§6](#6-request-semantics).
- **Booleans & enums**: Strongly typed; never stringly booleans
- **Money**: Integer minor units + currency code
- **Lists**: Arrays; use `[]` not `null`
- **Envelope**:
  - **Lists**: Use `items` array with optional top-level `page_info` for pagination
  - **Single objects**: Return fields directly at top level (no wrapper)

```json
// List response
{
  "items": [ /* array of objects */ ],
  "page_info": { /* optional: limit, next_cursor, prev_cursor */ }
}

// Single object response (no wrapper)
{
  "id": "018f6c9e-2c3b-7b1a-8f4a-9c3d2b1a0e5f",
  "title": "Example",
  "created_at": "2025-09-01T20:00:00.000Z"
}
```

## 5. Pagination, Filtering, Sorting, Field Projection

For the complete specification see [QUERYING.md](QUERYING.md):

- **Cursor pagination**: Opaque, versioned cursors with `limit` and `cursor` parameters.
  `limit` defaults and caps are defined once in [CONSTANTS.md](CONSTANTS.md); an
  out-of-range `limit` is rejected with `422 INVALID_LIMIT`, never clamped.
- **Filtering**: OData `$filter` with operators (`eq`, `ne`, `gt`, `in`, etc.)
- **Sorting**: OData `$orderby` (e.g., `priority desc,created_at asc`)
- **Field projection**: OData `$select` for sparse field selection (e.g., `$select=id,title`)
- **Counting**: `page_info` MUST NOT carry `total_count`. Endpoints that need a count expose
  `GET /resources:count?$filter=…` returning `{ count, exact }`.
- **Relation expansion**: not supported. `$expand` is the planned mechanism and has not
  shipped; there is deliberately no interim alternative — see [§23](#23-performance--dos).

## 6. Request Semantics

- **Create**: `POST /tickets` → 201 + `Location` + resource in body
- **Partial update**: `PATCH /tickets/{id}` — JSON Merge Patch
  ([RFC 7396](https://www.rfc-editor.org/rfc/rfc7396))
- **Replace**: `PUT /tickets/{id}` (complete representation)
- **Delete**: `DELETE /tickets/{id}` → 204; if soft-delete, return 200 with `deleted_at`

### JSON Merge Patch semantics

RFC 7396 uses `null` as its **delete sentinel**, which is the one place the
"prefer omitting absent fields over `null`" rule of [§4](#4-json-conventions) does not apply.
Implementations that strip nulls from request bodies silently break field clearing.

- `null` in a Merge Patch request body MUST be interpreted as "clear this field". It is the
  only context in which `null` is permitted on the wire.
- Omitting a field means "leave unchanged". Merge Patch therefore cannot distinguish
  "set to null" from "leave unchanged" for a field the client does not send — that is a
  property of the format, not a defect.
- **Array-valued fields are replaced in full.** Merge Patch has no element-level update. For
  element-level changes, model the collection as a sub-resource or use a batch endpoint
  (see [§19](#19-batch--bulk)).
- Servers MUST accept `Content-Type: application/merge-patch+json` and SHOULD also accept
  `application/json` for `PATCH`.

## 7. Error Model (Problem Details)

- **Always** return RFC 9457 Problem Details for 4xx/5xx, with
  `Content-Type: application/problem+json`. The one exception is batch endpoints — see
  [Batch exception](#batch-exception) below.

```json
{
  "type": "https://api.example.com/errors/validation-error",
  "code": "VALIDATION_ERROR",
  "title": "Invalid request",
  "status": 422,
  "detail": "email is invalid",
  "instance": "https://api.example.com/req/018f6c9e-3d4e-7f5a-8b6c-7d8e9f0a1b2c",
  "errors": [
    { "field": "email", "code": "format", "message": "must be a valid email" }
  ],
  "trace_id": "018f6c9e-3d4e-7f5a-8b6c-7d8e9f0a1b2c"
}
```

### The `code` member

`code` is a **REQUIRED** extension member of every Problem Details body. Without it the
application error catalogue is unreachable on the wire: `type` is a URI meant for humans and
`errors[].code` is field-level validation detail, not a request-level code.

- `code` is `SCREAMING_SNAKE_CASE` and **stable across versions**. It is a wire contract
  (PLID-31.03) and MUST NOT be renamed without a major version bump.
- [STATUS_CODES.md](STATUS_CODES.md) is the registry. Every code used anywhere in the API
  MUST appear there exactly once, against exactly one HTTP status.
- `errors[].code` is unrelated to the top-level `code`; it identifies a field-level
  validation failure (`format`, `required`, `out_of_range`).

### The `type` URI

- Template: `https://api.example.com/errors/{code-in-kebab-case}` — `INVALID_CURSOR` becomes
  `https://api.example.com/errors/invalid-cursor`.
- `type` and `code` are **1:1**. Each `code` has exactly one `type`, and each `type` resolves
  back to exactly one `code`.
- The namespace is owned by the API publisher, under a domain they control.
- A `type` URI SHOULD dereference to human-readable documentation for that error. It is not
  required to, and clients MUST NOT dereference it at runtime to decide behaviour — that is
  what `code` is for.
- For an error with no documented code, use `about:blank` (RFC 9457 §4.2.1) as the `type`.
  Such a response still carries a `code`: the generic code registered for that status.

### Localization

Errors are not localized on the wire. Clients localize by **`code`**, which is stable and
enumerable. `title` and `detail` are English diagnostics intended for developers and logs and
MUST NOT be displayed to end users.

### Batch exception

Batch endpoints return the batch **envelope**, not a Problem Details document, because the
response describes many outcomes rather than one:

- `200`, `207` and the all-failed aggregate status return `application/json` containing an
  `items` array.
- Each failed item's `error` member is a full Problem Details **object inside that envelope**,
  including its `code`.
- Only a batch-level failure that produces no envelope at all (a malformed batch request, a
  cross-item conflict, an atomic rollback) returns `application/problem+json`.

See [BATCH.md](BATCH.md) for the complete specification.

- **Mappings**: 400 (unparseable or unknown identifier), 401/403 (authn/authz), 404, 409
  (conflict), 412 (precondition), 422 (value violates a documented constraint), 429, 5xx
  (no internals). The 400-vs-422 decision rule lives in
  [STATUS_CODES.md](STATUS_CODES.md).

## 8. Concurrency & Idempotency

- **Optimistic locking**: Representations carry `ETag` (strong or weak). Clients send
  `If-Match`. On mismatch → 412.
- **Idempotency**: Clients SHOULD send `Idempotency-Key` on `POST`, `PATCH` and `DELETE`;
  servers MUST honour it on those methods.
  - Server caches **only successful (2xx) responses** to prevent duplicate side effects.
  - Error responses (4xx/5xx) are NOT cached; retries re-execute to allow fresh validation,
    permission checks, and recovery from transient failures.
  - Successful replays return the cached response with header: `Idempotency-Replayed: true`.
  - **Retention tiers** (values in [CONSTANTS.md](CONSTANTS.md)):
    - Minimum default: 1 hour (sufficient for network retry protection)
    - Important operations: 24h–7d (e.g., notifications, reports) — MUST be documented per endpoint
    - Critical operations: permanent via DB uniqueness constraints (e.g., payments, user
      registration) → return `409 Conflict` with the existing resource after initial creation

### Key format

`Idempotency-Key` MUST be 1–255 characters of printable US-ASCII (`%x21-7E`). UUIDv7 or ULID
are RECOMMENDED. A key outside that shape is rejected with `400 INVALID_IDEMPOTENCY_KEY` —
without a stated format, servers cannot validate it at all.

### Replay with a different body

The server computes a **request fingerprint** over the method, the path and the canonical
request body, and stores it with the key. If the same key arrives with a different
fingerprint, the server MUST reject the request with `422 IDEMPOTENCY_KEY_REUSED` rather than
executing it or replaying the earlier response. Silently replaying would return a response
that does not correspond to the request that was sent.

### Concurrent replay

If a request arrives with a key whose first request is **still executing**, the server MUST
return `409 IDEMPOTENCY_IN_PROGRESS` with a `Retry-After` header. Without this rule
implementations either double-execute the operation or serialise callers into timeouts.

## 9. Authentication & Authorization
- **Auth**: OAuth2/OIDC Bearer tokens in `Authorization: Bearer <token>`
- **Scopes/permissions**: Document per endpoint; insufficient → 403
- **Service-to-service**: mTLS optional
- **No secrets in URLs**; short token TTLs; rotate keys; refresh tokens when needed

## 10. Rate Limiting & Quotas

- **Headers** (following [draft-ietf-httpapi-ratelimit-headers](https://datatracker.ietf.org/doc/draft-ietf-httpapi-ratelimit-headers/), revision 11):
  - `RateLimit-Policy: "default";q=100;w=3600` (defines quota policy: 100 requests per hour)
  - `RateLimit: "default";r=72;t=1800` (current status: 72 remaining, resets in 1800 seconds)
- On 429 also include `Retry-After` (seconds). Quotas are per token by default.
- **Example with partition key**: `RateLimit-Policy: "peruser";q=100;w=60;pk=:dXNlcjEyMw==:`
- **Backward compatibility**: For legacy clients, servers **MAY** also return traditional
  `X-RateLimit-Limit`, `X-RateLimit-Remaining`, and `X-RateLimit-Reset` headers alongside the
  standard headers during a transition period.
- **Note**: This is an Internet-Draft, not an RFC, and its field syntax has changed across
  revisions. Pin the revision you implement and re-verify before shipping. The draft uses
  structured field syntax with parameters (not separate headers).

## 11. Asynchronous Operations
- For long tasks return `202 Accepted` + `Location: /jobs/{job_id}`
- **Job resource** example:

```json
{
  "id": "01J...",
  "status": "queued|running|succeeded|failed|canceled",
  "percent": 35,
  "result": {},
  "error": {},
  "created_at": "...",
  "updated_at": "..."
}
```

- Clients poll `GET /jobs/{id}` or subscribe via SSE/WebSocket if available

## 12. Webhooks (Outbound)
- **Event shape**: `event_type`, `id`, `created_at`, `data`
- **Delivery**: POST JSON to subscriber URL
- **Security**: `X-Signature` HMAC-SHA256 over raw body with shared secret; include `X-Timestamp` (±5 min skew)
- **Retries**: Exponential backoff for ≥24h; dead-letter queue
- **Idempotency**: Include `event_id`; receivers dedupe

## 13. Internationalization, Numbers & Time

- **Response timestamps** MUST be UTC (`Z`) and MUST include exactly three fractional digits
  `.SSS` (e.g., `2025-09-01T20:00:00.000Z`). If a timezone is needed, add a separate
  `timezone` field (IANA name).
- **Request inputs**, including `$filter` timestamp literals, accept any valid RFC 3339 form;
  milliseconds are not required there. The `.SSS` rule is a rule about what the API emits,
  not about what it will parse.
- JSON numbers for typical values; use strings for high-precision decimals or use integer minor units
- Sorting/filters are locale-agnostic unless documented otherwise
- Errors are not localized on the wire; clients localize by `code`
  (see [§7](#7-error-model-problem-details)).

## 14. Caching

- Reads: `ETag` + `Cache-Control: private, max-age=30` when safe
- Mutations: `Cache-Control: no-store`
- Conditional: `If-None-Match` → 304

## 15. Security & CORS

- HTTPS only; HSTS enabled
- CORS allow-list explicit origins; example:

```text
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Methods: GET,POST,PUT,PATCH,DELETE,OPTIONS
Access-Control-Allow-Headers: Authorization, Content-Type, Idempotency-Key, If-Match, If-None-Match
Access-Control-Expose-Headers: ETag, Location, RateLimit, RateLimit-Policy, Retry-After, Deprecation, Sunset, Idempotency-Replayed, X-Trace-Id, X-Request-Id
```

Every header a browser client is expected to read MUST appear in
`Access-Control-Expose-Headers`. A header the server sends but does not expose is invisible
to `fetch()` — which is how diagnostic and rate-limit headers silently disappear for SPA
clients.

- CSRF: only relevant for cookie auth; prefer Bearer in `Authorization` for SPAs
- Content Security Policy on the app domain; avoid wildcard source expressions such as
  `default-src *` or `script-src 'unsafe-inline'`

## 16. Observability & Diagnostics

- **Tracing**: accept/propagate `traceparent` (W3C). Emit **`X-Trace-Id`** on all responses.
- **Header naming**: the wire header is `X-Trace-Id`. `trace_id` is the JSON member in
  Problem Details bodies and the structured-log field name — it MUST NOT be used as an HTTP
  header name, because nginx drops underscored header names by default
  (`underscores_in_headers off`) and the value would silently vanish behind a common proxy.
- **Request ID**: honor `X-Request-Id` or generate one
- **Structured logs**: JSON per request: `trace_id`, `request_id`, `user_id`, `path`,
  `status`, `duration_ms`, `bytes`
- **Metrics**: RED/USE per route, with p50/p90/p99

## 17. Versioning & Deprecation

Quick reference:

- **Path versioning**: `/v1` (breaking changes bump major). Pre-release tiers are an
  environment dimension, not a path segment.
- **Stability tiers**: `stable`, `preview`, `experimental`, `deprecated`, `retired` — the
  same vocabulary as [PLID-10.02](../public-interface/PLID.md).
- **Non-breaking changes**: Adding optional fields/params, new endpoints, new enum values,
  relaxing validation
- **Breaking changes**: Removing fields, changing types/semantics, making optional fields
  required, changing URL structure
- **Client compatibility**: Must ignore unknown fields, handle new enum values gracefully,
  not rely on field order
- **Deprecation headers**: `Deprecation: @<unix-seconds>`
  ([RFC 9745](https://www.rfc-editor.org/rfc/rfc9745) — a structured-field Date, **not**
  `true`), `Sunset: <RFC 8594 HTTP-date>`, and `Link: <doc>; rel="deprecation"`.
- A deprecated but not yet retired endpoint keeps working and returns its normal status
  codes. `410 Gone` is for **retired** endpoints only.

For the complete specification see [VERSIONING.md](VERSIONING.md).

## 18. Canonical Status Codes

For complete HTTP status code definitions, the 400-vs-422 decision rule, and the application
error code registry, see [STATUS_CODES.md](STATUS_CODES.md).

Quick reference:

- 200 OK (read/update)
- 201 Created (+ `Location`)
- 202 Accepted (async)
- 204 No Content (delete or idempotent update without body)
- 207 Multi-Status (batch, mixed outcomes)
- 304 Not Modified (conditional GET)
- 400 Bad Request (unparseable, or an identifier outside the allowlist)
- 401 Unauthorized / 403 Forbidden
- 404 Not Found
- 409 Conflict
- 410 Gone (endpoints retired after their sunset date; expired async jobs)
- 412 Precondition Failed (ETag)
- 415 Unsupported Media Type
- 422 Unprocessable Entity (parses, but a value violates a documented constraint)
- 429 Too Many Requests
- 503 Service temporarily overloaded or under maintenance
- 5xx Other Server errors

## 19. Batch & Bulk

For the complete batch and bulk operations specification including error formats, atomicity
options, and idempotency, see [BATCH.md](BATCH.md).

**Quick Summary:**

- **Endpoint pattern**: one batch endpoint = one operation —
  `POST /resources:batch` (create), `POST /resources:batchUpdate`,
  `POST /resources:batchDelete`. The presence of `id` in an item never changes the operation.
- **Request limit**: default maximum 100 items, configurable per endpoint — see
  [CONSTANTS.md](CONSTANTS.md)
- **Response**: `207 Multi-Status` (partial success) or a specific status code (all same outcome)
- **Error format**: full RFC 9457 Problem Details per failed item, inside the batch envelope
  (see the [batch exception](#batch-exception) in §7)
- **Atomicity**: Endpoint-specific (best-effort default, atomic for critical operations)
- **Idempotency**: Per-item `idempotency_key`, tiered retention with a 1 h minimum (see BATCH.md)
- **Optimistic locking**: Per-item `if_match` field for version checking

## 20. OpenAPI & Codegen
- **Source of truth**: OpenAPI 3.1
- For Rust backend specifics (utoipa, serde, validator), see `RUST.md`
- Client SDK: generate TypeScript types (`openapi-typescript`) and React hooks (TanStack Query) with fetch/axios adapter
- Keep schemas DRY via shared components; provide example payloads for every operation

## 21. Example Endpoints

- **List Tickets**

```bash
curl -sS \
  -H "Authorization: Bearer $TOKEN" \
  "https://api.example.com/v1/tickets?limit=25&\$filter=status in ('open','in_progress')&\$orderby=priority desc,created_at asc&\$select=id,title,priority,status,created_at"
```

```json
{
  "items": [
    { "id": "018f6c9e-2c3b-7b1a-8f4a-9c3d2b1a0e5f", "title": "Disk full", "priority": "high", "status": "open", "created_at": "2025-08-31T10:05:17.000Z" }
  ],
  "page_info": {
    "limit": 25,
    "next_cursor": "eyJ2IjoyLCJrIjpbMywiMjAyNS0wOC0zMVQxMDowNToxNy4wMDBaIiwiMDE4ZjZjOWUtMmMzYi03YjFhLThmNGEtOWMzZDJiMWEwZTVmIl0sInMiOiItcHJpb3JpdHksK2NyZWF0ZWRfYXQsK2lkIiwiZCI6Im5leHQiLCJmIjoiYjdlZTJmMzU2NGI2IiwicCI6IjJlOGY1M2ExOTliNSJ9"
  }
}
```

The cursor decodes to:

```json
{"v":2,"k":[3,"2025-08-31T10:05:17.000Z","018f6c9e-2c3b-7b1a-8f4a-9c3d2b1a0e5f"],"s":"-priority,+created_at,+id","d":"next","f":"b7ee2f3564b6","p":"2e8f53a199b5"}
```

Reading it against [QUERYING.md](QUERYING.md): `s` carries all three sort tokens with explicit
per-token directions, matching the `$orderby` that was sent; `k` carries one value per token;
`f` is the hash of the normalized `$filter`; `p` is the hash of the sorted `$select` list.
`prev_cursor` is omitted because this is the first page — an absent cursor is omitted, never
sent as `null`.

Two endpoint-specific notes this example depends on:

- `/v1/tickets` extends the default ordering allowlist (`created_at`, `id`) with `priority`.
- `priority` sorts by an **ordinal**, not by its string value: `low` = 1, `medium` = 2,
  `high` = 3. That ordinal is what appears in the cursor's `k`, which is why `k[0]` is `3`
  and not `"high"`. Any endpoint adding an ordering field whose sort value differs from its
  display value MUST document the mapping.

- **Update with Concurrency**

```text
PATCH /v1/tickets/018f6c9e-2c3b-7b1a-8f4a-9c3d2b1a0e5f
If-Match: W/"etag-abc"
Idempotency-Key: 018f6c9e-6a71-7c8d-8e9f-0a1b2c3d4e5f
Content-Type: application/merge-patch+json

{ "status": "in_progress", "assignee_id": null }
```

`"assignee_id": null` clears the field — the Merge Patch delete sentinel from
[§6](#6-request-semantics).

- **Async Job**

```text
POST /v1/reports → 202 Accepted
Location: /v1/jobs/018f6c9e-4e5f-7a6b-8c7d-9e0f1a2b3c4d
Retry-After: 5
```

## 22. Backward Compatibility Rules (Client-facing)

- Clients ignore unknown fields
- Do not rely on property order
- Treat enums laxly: unknown enum → display as string, never crash
- Handle pagination cursors generically and treat them as fully opaque

## 23. Performance & DoS

- Enforce max list limits and payload sizes — see [CONSTANTS.md](CONSTANTS.md)
- Deny N+1 by default. Relation expansion is **not supported**: there is no `include=`
  parameter and no other interim mechanism. `$expand` is the planned mechanism
  ([QUERYING.md](QUERYING.md)); until it ships, clients fetch related resources in separate
  requests. Offering two unaware mechanisms is how the two documents drifted apart in the
  first place.
- Timeouts: handler ≤ 30s; use async jobs for longer work
- Strict input validation with precise 422s

## 24. Documentation Style

Each endpoint MUST be comprehensively documented to serve both human developers and AI assistants.

### Required Documentation Elements

1. **Summary & Description**
   - One-line summary
   - Detailed purpose explanation
   - When to use this endpoint

2. **Authentication & Authorization**
   - Required authentication method
   - Required scopes/permissions

3. **Request Specification**
   - HTTP method and path
   - Path parameters (type, format, constraints)
   - Query parameters (defaults, validation)
   - Request headers (required and optional)
   - Request body schema with field descriptions

4. **Response Specification**
   - Success status codes
   - Response headers
   - Response body schema
   - Example successful responses

5. **Error Documentation**
   - All possible error status codes
   - Problem Details examples for each, including the `code` member
   - Common error scenarios

6. **Rate Limiting**
   - Rate limit class
   - Quota consumption

7. **Code Examples**
   - curl with realistic data
   - TypeScript with generated client

### Documentation Template

**Endpoint**: `POST /v1/resources`
**Purpose**: Create new resource
**Authentication**: Required (OAuth2)
**Authorization**: `resources:write` scope
**Rate Limit**: Standard (100/hour)

**Request Body Schema**:

```json
{
  "title": "string (required, max 255 chars)",
  "description": "string (optional, max 1000 chars)",
  "priority": "enum: low|medium|high",
  "category": "string (optional)"
}
```

**Success Response** (201):

```json
{
  "id": "018f6c9e-5f60-7b7c-8d8e-9f0a1b2c3d4e",
  "title": "string",
  "description": "string",
  "priority": "medium",
  "category": "string",
  "status": "active",
  "created_at": "2024-01-15T10:30:00.000Z",
  "updated_at": "2024-01-15T10:30:00.000Z"
}
```

**Error Responses**:

- **400**: Unparseable request body
- **401**: Missing/invalid authentication
- **403**: Insufficient permissions
- **422**: Validation errors (Problem Details)
- **429**: Rate limit exceeded

**Code Examples**:

```bash
curl -X POST https://api.example.com/v1/resources \
  -H "Authorization: Bearer eyJ..." \
  -H "Content-Type: application/json" \
  -d '{"title": "Example", "priority": "medium"}'
```

```typescript
const resource = await api.createResource({
  title: 'Example',
  priority: 'medium'
});
```

Every example in an endpoint's documentation MUST satisfy the rules of this guideline —
identifiers are hyphenated UUIDv7, response timestamps carry `.SSS`, and error bodies carry
`code`. The PR checklist and the Spectral ruleset both check this.


## Operational Headers (Quick Reference)

- Requests may include: `Authorization`, `Idempotency-Key`, `If-Match`, `If-None-Match`,
  `Accept-Encoding`, `traceparent`, `X-Request-Id`
- Responses should include: `Content-Type`, `ETag` (when cacheable), `Location` (201/202),
  `RateLimit`, `RateLimit-Policy`, `X-Trace-Id`, `X-Request-Id`
- Conditional: `Retry-After` (429, 503, non-terminal async jobs, `IDEMPOTENCY_IN_PROGRESS`),
  `Idempotency-Replayed` (idempotent replay), `Deprecation` + `Sunset` + `Link`
  (deprecated endpoints)
- Every response header a browser client must read also belongs in
  `Access-Control-Expose-Headers` — see [§15](#15-security--cors).

## Constants

Every numeric constant in this guideline — limits, caps, retention windows, timeouts — is
defined once in [CONSTANTS.md](CONSTANTS.md). Reference it rather than restating a number.

## References

- RFC 9457 Problem Details: <https://www.rfc-editor.org/rfc/rfc9457>
- RFC 7396 JSON Merge Patch: <https://www.rfc-editor.org/rfc/rfc7396>
- RFC 9562 UUID (including UUIDv7): <https://www.rfc-editor.org/rfc/rfc9562>
- RFC 9110 HTTP Semantics: <https://www.rfc-editor.org/rfc/rfc9110>
- RFC 8594 Sunset HTTP Header: <https://www.rfc-editor.org/rfc/rfc8594>
- RFC 9745 Deprecation HTTP Header: <https://www.rfc-editor.org/rfc/rfc9745>
- IETF RateLimit Headers Draft (rev 11): <https://datatracker.ietf.org/doc/draft-ietf-httpapi-ratelimit-headers/>
- W3C Trace Context: <https://www.w3.org/TR/trace-context/>
