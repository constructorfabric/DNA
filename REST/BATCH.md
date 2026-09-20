# Batch & Bulk Operations

This document specifies how to design and implement batch/bulk endpoints in REST APIs following the Cyber Fabric guidelines.

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

- **Batch writes**: `POST /resources:batch`
- **Batch reads**: Use filters on collection endpoints (e.g., `GET /tickets?id.in=01J...,01K...`)
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
      "location": "/v1/tickets/01J...",
      "etag": "W/\"abc123\"",
      "data": {
        "id": "01J...",
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
        "type": "https://api.example.com/errors/validation",
        "title": "Validation failed",
        "status": 422,
        "detail": "Multiple validation errors",
        "instance": "https://api.example.com/req/01JXYZ...Z#item-1",
        "errors": [
          {
            "field": "priority",
            "code": "enum",
            "message": "must be low, medium, or high"
          }
        ],
        "trace_id": "01JXYZ...Z-item-1"
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
      "location": "/v1/tickets/01J...",
      "etag": "W/\"abc123\"",
      "data": { "id": "01J...", "title": "..." }
    },
    {
      "index": 1,
      "idempotency_key": "req-2",
      "status": 201,
      "location": "/v1/tickets/01K...",
      "etag": "W/\"def456\"",
      "data": { "id": "01K...", "title": "..." }
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
    "type": "https://api.example.com/errors/validation",
    "title": "Validation failed",
    "status": 422,
    "detail": "Multiple validation errors",
    "instance": "https://api.example.com/req/01JXYZ...Z#item-1",
    "errors": [
      { "field": "email", "code": "format", "message": "must be a valid email" },
      { "field": "priority", "code": "enum", "message": "must be low, medium, or high" }
    ],
    "trace_id": "01JXYZ...Z-item-1"
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
    "title": "Resource not found",
    "status": 404,
    "detail": "Ticket with id '01JOLD...' does not exist",
    "instance": "https://api.example.com/req/01JXYZ...Z#item-2",
    "trace_id": "01JXYZ...Z-item-2"
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
  "trace_id": "01JXYZ...Z"
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
    "title": "Resource conflict",
    "status": 409,
    "detail": "A ticket with title 'Fix login bug' already exists",
    "existing_resource_id": "01HOLD...",
    "trace_id": "01JXYZ...Z-item-2"
  }
}
```

## Optimistic Locking

Batch operations support per-item optimistic locking via the `if_match` field to prevent lost updates when multiple clients modify the same resources concurrently.

### Request with Version Checks

Each item may include an optional `if_match` field containing the ETag from a previous read:

```json
{
  "items": [
    {
      "idempotency_key": "req-1",
      "if_match": "W/\"abc123\"",
      "data": {
        "id": "01JTKT...",
        "status": "completed"
      }
    },
    {
      "idempotency_key": "req-2",
      "if_match": "W/\"def456\"",
      "data": {
        "id": "01JTKU...",
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
        "title": "Precondition failed",
        "status": 412,
        "detail": "Resource was modified since last read. ETag mismatch.",
        "trace_id": "01JXYZ...Z-item-0"
      }
    },
    {
      "index": 1,
      "idempotency_key": "req-2",
      "status": 200,
      "etag": "W/\"ghi012\"",
      "data": {
        "id": "01JTKU...",
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
  "title": "Batch operation failed",
  "status": 422,
  "detail": "Transaction rolled back due to validation failure at item 3",
  "failed_item_index": 3,
  "item_error": {
    "errors": [
      { "field": "amount", "code": "range", "message": "must be positive" }
    ]
  },
  "trace_id": "01JXYZ...Z"
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
- **Idempotency retention** (tiered by operation criticality):
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
  "location": "/v1/tickets/01J...",
  "etag": "W/\"abc123\"",
  "idempotency_replayed": true,
  "data": { "id": "01J...", "title": "..." }
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
          "assignee_id": "01JUSR..."
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
trace_id: 01JXYZ...Z
```

```json
{
  "items": [
    {
      "index": 0,
      "idempotency_key": "req-1",
      "status": 201,
      "location": "/v1/tickets/01JTKT...",
      "etag": "W/\"abc123\"",
      "data": {
        "id": "01JTKT...",
        "title": "Fix login bug",
        "priority": "high",
        "status": "open",
        "assignee_id": "01JUSR...",
        "created_at": "2025-09-01T20:00:00.000Z",
        "updated_at": "2025-09-01T20:00:00.000Z"
      }
    },
    {
      "index": 1,
      "idempotency_key": "req-2",
      "status": 201,
      "location": "/v1/tickets/01JTKU...",
      "etag": "W/\"def456\"",
      "data": {
        "id": "01JTKU...",
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
        "type": "https://api.example.com/errors/validation",
        "title": "Validation failed",
        "status": 422,
        "detail": "Invalid priority value",
        "instance": "https://api.example.com/req/01JXYZ...Z#item-2",
        "errors": [
          {
            "field": "priority",
            "code": "enum",
            "message": "must be low, medium, or high"
          }
        ],
        "trace_id": "01JXYZ...Z-item-2"
      }
    }
  ]
}
```
