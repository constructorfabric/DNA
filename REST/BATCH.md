# Batch & Bulk Operations

This document specifies how to design and implement batch/bulk endpoints in REST APIs following the DNA guidelines.

## Table of Contents
- [Endpoint Pattern](#endpoint-pattern)
- [Request Format](#request-format)
- [Response Formats](#response-formats)
- [Status Code Rules](#status-code-rules)
- [Error Format](#error-format)
- [Cross-Item Conflicts](#cross-item-conflicts)
- [Optimistic Locking](#optimistic-locking)
- [Atomicity (Transactional Semantics)](#atomicity-transactional-semantics)
- [Idempotency](#idempotency)
- [Performance Limits](#performance-limits)
- [Complete Example](#complete-example)

## Endpoint Pattern

**One batch endpoint = one operation.** The endpoint determines the operation applied to
every item in the batch; the presence or absence of `id` in an item's `data` MUST NOT
change it.

- **Batch create**: `POST /resources:batch` — items carry `data` without `id`.
- **Batch update**: `POST /resources:batchUpdate` — items carry `data` with `id` plus the
  fields to update (JSON Merge Patch semantics).
- **Batch delete**: `POST /resources:batchDelete` — items carry `id` only.
- **Batch reads**: Use filters on collection endpoints (e.g.,
  `GET /tickets?id.in=018f6c9e-2c3b-7b1a-8f4a-9c3d2b1a0e5f,018f6c9e-1a2b-7c3d-9e4f-5a6b7c8d9e0f`)
- **Response**: `207 Multi-Status` (partial success) or specific status code (all same outcome)
- **Request limit**: Default 100 items per batch (configurable per endpoint, must be documented)

## Request Format

Each item in a batch request contains:
- `idempotency_key` (optional): Unique identifier for idempotent processing
- `if_match` (optional): ETag value for optimistic locking
- `data` (required): The resource data for this operation

```json
{
  "items": [
    {
      "idempotency_key": "req-1",
      "data": {
        "title": "Fix login bug",
        "priority": "high"
      }
    },
    {
      "idempotency_key": "req-2",
      "data": {
        "title": "Update documentation",
        "priority": "medium"
      }
    }
  ]
}
```

## Response Formats

Each item in a batch response contains:
- `index` (required): Zero-based position in the request array
- `idempotency_key` (if provided): Echoed from request for correlation
- `status` (required): HTTP status code for this item
- `data` (success case): The resource representation
- `error` (failure case): RFC 9457 Problem Details
- `location` (optional): URI of created/modified resource
- `etag` (optional): Current version identifier for the resource
- `idempotency_replayed` (optional): Present and `true` if response was replayed from cache

### Content Type Rule

Batch **envelope** responses — `200`, `207`, and the all-failed aggregate that still
carries an `items` array — use `Content-Type: application/json`; the per-item `error`
objects are RFC 9457 Problem Details **inside** that envelope, not the response's own
Content-Type. Only batch-level failures that return no envelope at all (see
[Cross-Item Conflicts](#cross-item-conflicts) and the atomic-failure response in
[Atomicity](#atomicity-transactional-semantics)) use `Content-Type: application/problem+json`.
See [API.md §7 Error Model](API.md#7-error-model-problem-details) for the single-item rule
this is an exception to.

### Partial Success

```http
HTTP/1.1 207 Multi-Status
Content-Type: application/json
```

```json
{
  "items": [
    {
      "index": 0,
      "idempotency_key": "req-1",
      "status": 201,
      "location": "/v1/tickets/018f6c9e-2c3b-7b1a-8f4a-9c3d2b1a0e5f",
      "etag": "W/\"abc123\"",
      "data": {
        "id": "018f6c9e-2c3b-7b1a-8f4a-9c3d2b1a0e5f",
        "title": "Fix login bug",
        "priority": "high",
        "status": "open",
        "created_at": "2025-09-01T20:00:00.000Z",
        "updated_at": "2025-09-01T20:00:00.000Z"
      }
    },
    {
      "index": 1,
      "idempotency_key": "req-2",
      "status": 422,
      "error": {
        "type": "https://api.example.com/errors/validation-error",
        "code": "VALIDATION_ERROR",
        "title": "Validation failed",
        "status": 422,
        "detail": "Multiple validation errors",
        "instance": "https://api.example.com/req/26e1d6c77e474d3b9272c5d82dba2b38#item-1",
        "errors": [
          {
            "field": "priority",
            "code": "enum",
            "message": "must be low, medium, or high"
          }
        ],
        "trace_id": "26e1d6c77e474d3b9272c5d82dba2b38-item-1"
      }
    }
  ]
}
```

### All Success

```http
HTTP/1.1 200 OK
Content-Type: application/json
```

```json
{
  "items": [
    {
      "index": 0,
      "idempotency_key": "req-1",
      "status": 201,
      "location": "/v1/tickets/018f6c9e-2c3b-7b1a-8f4a-9c3d2b1a0e5f",
      "etag": "W/\"abc123\"",
      "data": { "id": "018f6c9e-2c3b-7b1a-8f4a-9c3d2b1a0e5f", "title": "..." }
    },
    {
      "index": 1,
      "idempotency_key": "req-2",
      "status": 201,
      "location": "/v1/tickets/018f6c9e-1a2b-7c3d-9e4f-5a6b7c8d9e0f",
      "etag": "W/\"def456\"",
      "data": { "id": "018f6c9e-1a2b-7c3d-9e4f-5a6b7c8d9e0f", "title": "..." }
    }
  ]
}
```

### All Failed (Same Error Type)

```http
HTTP/1.1 422 Unprocessable Entity
Content-Type: application/json
```

```json
{
  "items": [
    { "index": 0, "status": 422, "error": { /* Problem Details */ } },
    { "index": 1, "status": 422, "error": { /* Problem Details */ } }
  ]
}
```

## Status Code Rules

The top-level HTTP status code reflects the aggregate outcome:

- **All succeeded** → `200 OK` (or `201 Created` if appropriate)
- **Partial success/failure** → `207 Multi-Status`
- **All failed (same error type)** → matching `4xx` (e.g., all `422` → top-level `422`)
- **All failed (mixed error types)** → `207 Multi-Status`

## Error Format

Each failed item receives **complete RFC 9457 Problem Details** for consistency with single-item error format (see [API.md §7 Error Model](API.md#7-error-model-problem-details)).

### Required Fields
- `type` - Error type URL
- `code` - Application error code (`SCREAMING_SNAKE_CASE`; see `STATUS_CODES.md`, the registry)
- `title` - Short error description
- `status` - HTTP status code for this item
- `trace_id` - Unique trace identifier for this item

### Optional Fields
- `detail` - Detailed explanation
- `instance` - Request URL with `#item-{index}` fragment
- `errors` - Array of field-level validation errors (for 422 responses)

### Example: Validation Error

```json
{
  "index": 1,
  "idempotency_key": "req-2",
  "status": 422,
  "error": {
    "type": "https://api.example.com/errors/validation-error",
    "code": "VALIDATION_ERROR",
    "title": "Validation failed",
    "status": 422,
    "detail": "Multiple validation errors",
    "instance": "https://api.example.com/req/ff151a5be7e137fa4c582f972d03ee14#item-1",
    "errors": [
      { "field": "email", "code": "format", "message": "must be a valid email" },
      { "field": "priority", "code": "enum", "message": "must be low, medium, or high" }
    ],
    "trace_id": "ff151a5be7e137fa4c582f972d03ee14-item-1"
  }
}
```

### Example: Not Found Error

```json
{
  "index": 2,
  "idempotency_key": "req-3",
  "status": 404,
  "error": {
    "type": "https://api.example.com/errors/not-found",
    "code": "NOT_FOUND",
    "title": "Resource not found",
    "status": 404,
    "detail": "Ticket with id '018f6c9e-3d4e-7f5a-8b6c-7d8e9f0a1b2c' does not exist",
    "instance": "https://api.example.com/req/ff151a5be7e137fa4c582f972d03ee14#item-2",
    "trace_id": "ff151a5be7e137fa4c582f972d03ee14-item-2"
  }
}
```

## Cross-Item Conflicts

Since cross-item conflicts (duplicates within the batch, constraint violations across items) are typically rare, use simple batch-level error reporting when detected.

### Pre-validation Approach

Stop processing and return single Problem Details:

```http
HTTP/1.1 400 Bad Request
Content-Type: application/problem+json
```

```json
{
  "type": "https://api.example.com/errors/batch-conflict",
  "code": "BATCH_CONFLICT",
  "title": "Duplicate items in batch",
  "status": 400,
  "detail": "Items at indices 1 and 3 have duplicate email addresses",
  "conflicts": [
    {
      "type": "duplicate",
      "field": "email",
      "value": "user@example.com",
      "item_indices": [1, 3]
    }
  ],
  "trace_id": "b6deb17be24d262bf70f9c64cc45430c"
}
```

### Conflicts with Existing Resources

Conflicts with existing resources (not within the batch) are treated as per-item 409 errors:

```json
{
  "index": 2,
  "idempotency_key": "req-3",
  "status": 409,
  "error": {
    "type": "https://api.example.com/errors/conflict",
    "code": "CONFLICT",
    "title": "Resource conflict",
    "status": 409,
    "detail": "A ticket with title 'Fix login bug' already exists",
    "existing_resource_id": "018f6c9e-4e5f-7a6b-8c7d-9e0f1a2b3c4d",
    "trace_id": "5f54953c6f6bb538c120eca52f75cb0b-item-2"
  }
}
```

## Optimistic Locking

Batch operations support per-item optimistic locking via the `if_match` field to prevent lost updates when multiple clients modify the same resources concurrently. These examples target `POST /tickets:batchUpdate` — every item carries `id` plus the fields to update.

### Request with Version Checks

Each item may include an optional `if_match` field containing the ETag from a previous read:

```json
{
  "items": [
    {
      "idempotency_key": "req-1",
      "if_match": "W/\"abc123\"",
      "data": {
        "id": "018f6c9e-5f60-7b7c-8d8e-9f0a1b2c3d4e",
        "status": "completed"
      }
    },
    {
      "idempotency_key": "req-2",
      "if_match": "W/\"def456\"",
      "data": {
        "id": "018f6c9e-6a71-7c8d-8e9f-0a1b2c3d4e5f",
        "priority": "high"
      }
    }
  ]
}
```

### Version Mismatch Handling

When `if_match` is provided and doesn't match the current resource version, the item fails with `412 Precondition Failed`:

```json
{
  "items": [
    {
      "index": 0,
      "idempotency_key": "req-1",
      "status": 412,
      "error": {
        "type": "https://api.example.com/errors/precondition-failed",
        "code": "PRECONDITION_FAILED",
        "title": "Precondition failed",
        "status": 412,
        "detail": "Resource was modified since last read. ETag mismatch.",
        "trace_id": "5dc71ccb1332700bf593fe6c3a001805-item-0"
      }
    },
    {
      "index": 1,
      "idempotency_key": "req-2",
      "status": 200,
      "etag": "W/\"ghi012\"",
      "data": {
        "id": "018f6c9e-6a71-7c8d-8e9f-0a1b2c3d4e5f",
        "priority": "high",
        "updated_at": "2025-09-01T20:01:00.000Z"
      }
    }
  ]
}
```

## Atomicity (Transactional Semantics)

Default behavior is **endpoint-specific** and must be documented for each batch operation.

### Best-Effort Endpoints (Default)

Most endpoints use **best-effort** semantics: each item is processed independently, and successes are committed even if other items fail.

**Request:**
```json
{
  "items": [ /* ... */ ]
}
```

**Response:** `207 Multi-Status` (or other status based on aggregate outcome) with per-item results showing mix of successes and failures.

**Use Cases:**
- Bulk user imports (independent records)
- Creating multiple independent tickets
- Batch notifications
- Log ingestion

### Atomic Endpoints (All-or-Nothing)

Some endpoints enforce **transactional** semantics: if any item fails, all changes are rolled back.

Document clearly in endpoint specification that atomic behavior applies.

**Response on Failure:**

```http
HTTP/1.1 422 Unprocessable Entity
Content-Type: application/problem+json
```

```json
{
  "type": "https://api.example.com/errors/batch-failed",
  "code": "BATCH_FAILED",
  "title": "Batch operation failed",
  "status": 422,
  "detail": "Transaction rolled back due to validation failure at item 3",
  "failed_item_index": 3,
  "item_error": {
    "errors": [
      { "field": "amount", "code": "range", "message": "must be positive" }
    ]
  },
  "trace_id": "c443d1b0c23fa56df7a3e2ba7d2151c6"
}
```

**Use Cases:**
- Financial transactions
- Creating related records that must coexist (parent + children)
- Critical business operations requiring consistency

### Client-Controlled Atomicity (Optional)

Some endpoints may support both modes via request parameter for maximum flexibility:

**Request:**
```json
{
  "atomic": true,
  "items": [ /* ... */ ]
}
```

- `"atomic": false` (or omitted) → best-effort (default)
- `"atomic": true` → all-or-nothing

## Idempotency

Batch operations support **per-item idempotency** to enable safe retries.

### Request with Idempotency Keys

```json
{
  "items": [
    {
      "idempotency_key": "user-action-123-item-0",
      "data": { "title": "Ticket 1", "priority": "high" }
    },
    {
      "idempotency_key": "user-action-123-item-1",
      "data": { "title": "Ticket 2", "priority": "medium" }
    }
  ]
}
```

### Server Behavior

- Each item's `idempotency_key` is matched independently
- Only **successful (2xx) outcomes** are cached and replayed with the original response
- Error responses (4xx/5xx) are **NOT cached**; retries re-execute to allow fresh validation, permission checks, and recovery from transient failures
- Mix of new and replayed items is allowed in a single batch

### Idempotency Retention

Retention is **tiered by operation criticality**:

- Minimum default: 1 hour (sufficient for network retry protection)
- Important operations: 24h-7d (e.g., bulk notifications, report generation)
- Critical operations: Permanent via DB uniqueness on `idempotency_key` (e.g., payment processing, invoice creation) → return `409 Conflict` per item if key exists after cache expiry

### Replayed Item Indication

When a request is replayed from the idempotency cache, the response includes `idempotency_replayed: true`:

```json
{
  "index": 0,
  "idempotency_key": "user-action-123-item-0",
  "status": 201,
  "location": "/v1/tickets/018f6c9e-2c3b-7b1a-8f4a-9c3d2b1a0e5f",
  "etag": "W/\"abc123\"",
  "idempotency_replayed": true,
  "data": { "id": "018f6c9e-2c3b-7b1a-8f4a-9c3d2b1a0e5f", "title": "..." }
}
```

## Performance Limits

- **Default maximum batch size**: 100 items per request (configurable per endpoint)
- **Default timeout**: 30s (same as single operations, configurable per endpoint)
- **Default maximum payload size**: 1MB for entire batch request (configurable per endpoint)
- **Rate limiting**: Batch operations count as a single request; consider separate quotas for batch vs single-item operations

## Complete Example

### Request

```bash
curl -X POST https://api.example.com/v1/tickets:batch \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -H "traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01" \
  -d '{
    "items": [
      {
        "idempotency_key": "req-1",
        "data": {
          "title": "Fix login bug",
          "priority": "high",
          "assignee_id": "018f6c9e-1a2b-7c3d-9e4f-5a6b7c8d9e0f"
        }
      },
      {
        "idempotency_key": "req-2",
        "data": {
          "title": "Update docs",
          "priority": "low"
        }
      },
      {
        "idempotency_key": "req-3",
        "data": {
          "title": "Invalid ticket",
          "priority": "invalid-value"
        }
      }
    ]
  }'
```

### Response (Partial Success)

```http
HTTP/1.1 207 Multi-Status
Content-Type: application/json
RateLimit-Policy: "default";q=100;w=3600
RateLimit: "default";r=99;t=3540
X-Trace-Id: 4bf92f3577b34da6a3ce929d0e0e4736
```

```json
{
  "items": [
    {
      "index": 0,
      "idempotency_key": "req-1",
      "status": 201,
      "location": "/v1/tickets/018f6c9e-3d4e-7f5a-8b6c-7d8e9f0a1b2c",
      "etag": "W/\"abc123\"",
      "data": {
        "id": "018f6c9e-3d4e-7f5a-8b6c-7d8e9f0a1b2c",
        "title": "Fix login bug",
        "priority": "high",
        "status": "open",
        "assignee_id": "018f6c9e-1a2b-7c3d-9e4f-5a6b7c8d9e0f",
        "created_at": "2025-09-01T20:00:00.000Z",
        "updated_at": "2025-09-01T20:00:00.000Z"
      }
    },
    {
      "index": 1,
      "idempotency_key": "req-2",
      "status": 201,
      "location": "/v1/tickets/018f6c9e-4e5f-7a6b-8c7d-9e0f1a2b3c4d",
      "etag": "W/\"def456\"",
      "data": {
        "id": "018f6c9e-4e5f-7a6b-8c7d-9e0f1a2b3c4d",
        "title": "Update docs",
        "priority": "low",
        "status": "open",
        "created_at": "2025-09-01T20:00:01.000Z",
        "updated_at": "2025-09-01T20:00:01.000Z"
      }
    },
    {
      "index": 2,
      "idempotency_key": "req-3",
      "status": 422,
      "error": {
        "type": "https://api.example.com/errors/validation-error",
        "code": "VALIDATION_ERROR",
        "title": "Validation failed",
        "status": 422,
        "detail": "Invalid priority value",
        "instance": "https://api.example.com/req/4bf92f3577b34da6a3ce929d0e0e4736#item-2",
        "errors": [
          {
            "field": "priority",
            "code": "enum",
            "message": "must be low, medium, or high"
          }
        ],
        "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736-item-2"
      }
    }
  ]
}
```
