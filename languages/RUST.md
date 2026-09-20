# Rust Backend — Implementation Guide

This file contains Rust-specific guidance and examples.

Every fenced ```rust block in this document is extracted, concatenated in
document order, and compiled as a single crate in CI (`ci/rust-examples/`,
see `ci/extract_rust_examples.py`). This enforces PLID-42.04 *Runnable &
Verified Examples*. Because the blocks share one flat module, an import
introduced in an earlier block is already in scope for later ones — later
blocks only add imports they need for the first time.

## Backend Stack & Libraries
- Routing/middleware: `axum`, `tower-http` (CORS, compression, timeouts)
- JSON & validation: `serde`, `validator`
- OpenAPI: `utoipa`, `utoipa-swagger-ui` (optional docs UI)
- Observability: `tracing`, `tracing-subscriber`, `tracing-opentelemetry`
- DB access: `sqlx` or `sea-orm`; use query builders for filters/sorts safely
- IDs & time: `uuid` (v7) or `ulid`; `time` crate for UTC (`OffsetDateTime`)

**Why `time`, not `chrono`:** DNA mandates the `time` crate for Rust services.
It has no default-timezone footgun (`chrono::Local` silently reads the host's
TZ database, which is rarely what a server wants), its `serde` integration is
first-party and covers RFC 3339 and custom format descriptions (see
Timestamps below), and it is actively maintained.
[PLID-11.04](../public-interface/PLID.md) is language-agnostic and names only the
stdlib `std::time::Duration`, deferring to this document for the date-time crate;
this document is the canonical Rust guidance and `time` is the DNA choice.

## OpenAPI Generation
- Annotate handlers with `utoipa::path`
- Export OpenAPI 3.1 JSON at `/v1/openapi.json`
- Validate in CI with an OpenAPI linter

## Data Types
```rust
use serde::{Deserialize, Serialize};
use time::OffsetDateTime;
use uuid::Uuid; // enable the v7 feature in Cargo.toml
use utoipa::ToSchema;

// RFC 9457 / this norm set requires response timestamps to be ISO-8601 UTC
// with exactly three fractional digits (`.SSS`). `time::serde::rfc3339`
// does NOT guarantee this — see the Timestamps section below for why. Pin
// the format explicitly instead of relying on the well-known RFC3339 module.
time::serde::format_description!(
    iso8601_millis,
    OffsetDateTime,
    "[year]-[month]-[day]T[hour]:[minute]:[second].[subsecond digits:3]Z"
);

#[derive(Debug, Serialize, Deserialize, ToSchema)]
#[serde(rename_all = "snake_case")]
pub struct Ticket {
    pub id: Uuid,
    pub title: String,
    pub priority: TicketPriority,
    pub status: TicketStatus,
    #[serde(with = "iso8601_millis")]
    pub created_at: OffsetDateTime,
    #[serde(with = "iso8601_millis")]
    pub updated_at: OffsetDateTime,
    #[serde(with = "iso8601_millis::option")]
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub deleted_at: Option<OffsetDateTime>,
}

#[derive(Debug, Serialize, Deserialize, ToSchema)]
#[serde(rename_all = "snake_case")]
pub enum TicketPriority { Low, Medium, High }

#[derive(Debug, Serialize, Deserialize, ToSchema)]
#[serde(rename_all = "snake_case")]
pub enum TicketStatus { Open, InProgress, Resolved, Closed }
```

## Error Handling (Problem Details)

```rust
use axum::http::{header, HeaderValue, StatusCode};
use axum::response::{IntoResponse, Response};

/// RFC 9457 Problem Details.
///
/// `code` is a REQUIRED, stable, SCREAMING_SNAKE_CASE wire contract — see
/// `STATUS_CODES.md`, the registry for every value this field may take.
/// `type` and `code` are 1:1 (`type` = `https://api.example.com/errors/{code
/// in kebab-case}`). `trace_id` here is the JSON member only; the HTTP header
/// is `X-Trace-Id` (see the handler below, and note on why not `trace_id`).
#[derive(Debug, Serialize, ToSchema)]
#[serde(rename_all = "snake_case")]
pub struct Problem {
    #[schema(example = "https://api.example.com/errors/invalid-limit")]
    pub r#type: String,
    #[schema(example = "limit out of range")]
    pub title: String,
    pub status: u16,
    #[schema(example = "INVALID_LIMIT")]
    pub code: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub detail: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub instance: Option<String>,
    pub trace_id: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub errors: Option<Vec<ValidationError>>,
}

#[derive(Debug, Serialize, ToSchema)]
pub struct ValidationError {
    pub field: String,
    pub code: String,
    pub message: String,
}

impl IntoResponse for Problem {
    fn into_response(self) -> Response {
        let status = StatusCode::from_u16(self.status).unwrap_or(StatusCode::INTERNAL_SERVER_ERROR);
        let mut response = (status, axum::Json(self)).into_response();
        // RFC 9457 §3: Problem Details responses MUST use this media type.
        response.headers_mut().insert(
            header::CONTENT_TYPE,
            HeaderValue::from_static("application/problem+json"),
        );
        response
    }
}
```

## axum Handler with utoipa
```rust
use axum::extract::Query;
use axum::http::HeaderMap;
use axum::Json;
use utoipa::openapi::extensions::Extensions;
use utoipa::{IntoParams, Modify, OpenApi};

/// See `REST/CONSTANTS.md` for the canonical values; do not restate the
/// literals in normative prose, only in code and examples.
pub const MIN_LIMIT: u16 = 1;
pub const DEFAULT_LIMIT: u16 = 25;
pub const MAX_LIMIT: u16 = 200;

#[derive(Debug, Deserialize, IntoParams)]
#[serde(deny_unknown_fields)]
pub struct ListParams {
    /// Page size. Out-of-range values are REJECTED with 422 `INVALID_LIMIT`,
    /// never clamped.
    #[param(example = 25)]
    pub limit: Option<u16>,

    /// Opaque cursor from a previous response's `page_info`. See
    /// QUERYING.md's Cursor Format for the (versioned) payload.
    #[param(example = "eyJ2IjoyLCJrIjpb...")]
    pub cursor: Option<String>,

    /// OData filter over the endpoint's allowlisted indexed fields.
    /// `IntoParams` does not read `serde`'s `rename`, so both attributes
    /// are required to keep the wire name and the generated OpenAPI in sync.
    #[serde(rename = "$filter")]
    #[param(rename = "$filter", example = "status in ('open','in_progress')")]
    pub filter: Option<String>,

    /// OData order-by; MUST include a unique tiebreaker last.
    #[serde(rename = "$orderby")]
    #[param(rename = "$orderby", example = "-priority,+created_at,+id")]
    pub orderby: Option<String>,

    /// Sparse field selection.
    #[serde(rename = "$select")]
    #[param(rename = "$select", example = "id,title,status,priority")]
    pub select: Option<String>,
}

#[derive(Debug, Serialize, ToSchema)]
#[serde(rename_all = "snake_case")]
pub struct ListResponse<T> {
    pub items: Vec<T>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub page_info: Option<PageInfo>,
}

#[derive(Debug, Serialize, ToSchema)]
#[serde(rename_all = "snake_case")]
pub struct PageInfo {
    pub limit: u16,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub next_cursor: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub prev_cursor: Option<String>,
}

/// Attaches the `x-odata-filter` vendor extension (allowlisted fields) to the
/// `$filter` parameter of `GET /v1/tickets`. `#[derive(IntoParams)]` has no
/// per-field hook for arbitrary vendor extensions, so this is done once, on
/// the generated document, via `utoipa::Modify` — the supported extension
/// point for exactly this kind of post-processing.
pub struct OdataExtensions;

impl Modify for OdataExtensions {
    fn modify(&self, openapi: &mut utoipa::openapi::OpenApi) {
        let Some(item) = openapi.paths.paths.get_mut("/v1/tickets") else {
            return;
        };
        let Some(operation) = item.get.as_mut() else {
            return;
        };
        let Some(parameters) = operation.parameters.as_mut() else {
            return;
        };
        for parameter in parameters.iter_mut() {
            if parameter.name == "$filter" {
                parameter.extensions = Some(Extensions::from_iter([(
                    "x-odata-filter",
                    serde_json::json!({ "allowedFields": ["status", "priority", "created_at"] }),
                )]));
            }
        }
    }
}

#[derive(OpenApi)]
#[openapi(paths(list_tickets), components(schemas(Ticket, Problem, ValidationError)), modifiers(&OdataExtensions))]
pub struct ApiDoc;

/// List tickets with cursor pagination.
#[utoipa::path(
    get,
    path = "/v1/tickets",
    params(ListParams),
    responses(
        (status = 200, description = "List tickets", body = ListResponse<Ticket>),
        (status = 400, description = "Malformed query", body = Problem),
        (status = 422, description = "Validation error", body = Problem)
    ),
    security(("oauth2" = []))
)]
pub async fn list_tickets(
    query: Result<Query<ListParams>, axum::extract::rejection::QueryRejection>,
) -> Result<impl IntoResponse, Problem> {
    // Unknown query parameters are rejected, not silently ignored, because
    // `ListParams` carries `#[serde(deny_unknown_fields)]`.
    let Query(params) = query.map_err(|err| Problem {
        r#type: "https://api.example.com/errors/invalid-query".to_string(),
        title: "invalid query parameters".to_string(),
        status: 400,
        code: "INVALID_QUERY".to_string(),
        detail: Some(err.to_string()),
        instance: None,
        trace_id: "018f6c9e-2c3b-7b1a-8f4a-9c3d2b1a0e5f".to_string(),
        errors: None,
    })?;

    // `limit` is rejected outside [MIN_LIMIT, MAX_LIMIT], never clamped.
    let limit = match params.limit.unwrap_or(DEFAULT_LIMIT) {
        n if (MIN_LIMIT..=MAX_LIMIT).contains(&n) => n,
        _ => {
            return Err(Problem {
                r#type: "https://api.example.com/errors/invalid-limit".to_string(),
                title: "limit out of range".to_string(),
                status: 422,
                code: "INVALID_LIMIT".to_string(),
                detail: Some(format!("limit must be between {MIN_LIMIT} and {MAX_LIMIT}")),
                instance: None,
                trace_id: "018f6c9e-2c3b-7b1a-8f4a-9c3d2b1a0e5f".to_string(),
                errors: None,
            });
        }
    };

    let cursor = params.cursor.clone();
    let filter = params.filter.clone();
    let orderby = params.orderby.clone();
    let select = params.select.clone();
    let _ = (cursor, filter, orderby, select); // fed into the query builder below

    // ... database logic to fetch tickets based on filters, select ...
    let tickets: Vec<Ticket> = vec![]; // Placeholder

    let response = ListResponse {
        items: tickets,
        page_info: Some(PageInfo {
            limit,
            next_cursor: None, // Compute from last item if has_more
            prev_cursor: None, // Compute from first item if not first page
        }),
    };

    // Build response with headers. `X-Trace-Id` — not `trace_id` — because
    // nginx drops underscored header names by default
    // (`underscores_in_headers off`); `trace_id` survives as the JSON member
    // above and as the structured-log field.
    let mut headers = HeaderMap::new();
    headers.insert(
        axum::http::HeaderName::from_static("x-trace-id"),
        "018f6c9e-2c3b-7b1a-8f4a-9c3d2b1a0e5f".parse().unwrap(),
    );
    Ok((headers, Json(response)))
}
```

## Keyset Pagination with `sqlx`

The recipe below follows QUERYING.md's v2 cursor format and its backward
pagination rule: the backward query inverts `ORDER BY` so `LIMIT` takes the
rows adjacent to the cursor, and the trimmed rows are re-reversed in memory
before serialising, so the response is always in canonical order even though
the query is not. This example binds parameters with plain `sqlx::query_as`
(no `query!` macro), so it compiles without a live database at build time.

```rust
use base64::engine::general_purpose::URL_SAFE_NO_PAD;
use base64::Engine as _;
use serde_json::Value as JsonValue;

/// Direction of travel, minted into the cursor (`d`) — this is what makes
/// backward navigation implementable through a single `cursor` parameter.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum Direction {
    Next,
    Prev,
}

/// Cursor payload v2 (QUERYING.md's Cursor Format). `k` holds one value per
/// token in `s`, in the same order. `v1` tokens (no `d`) are rejected by
/// callers with 400 `INVALID_CURSOR` before reaching this type.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CursorV2 {
    pub v: u8,
    pub k: Vec<JsonValue>,
    pub s: String,
    pub d: Direction,
    pub f: Option<String>,
    pub p: Option<String>,
}

#[derive(Debug)]
pub struct CursorDecodeError; // maps to 400 INVALID_CURSOR at the handler boundary

impl CursorV2 {
    pub fn encode(&self) -> String {
        let json = serde_json::to_vec(self).expect("CursorV2 is always serializable");
        URL_SAFE_NO_PAD.encode(json)
    }

    pub fn decode(token: &str) -> Result<Self, CursorDecodeError> {
        let bytes = URL_SAFE_NO_PAD.decode(token).map_err(|_| CursorDecodeError)?;
        let cursor: CursorV2 = serde_json::from_slice(&bytes).map_err(|_| CursorDecodeError)?;
        if cursor.v != 2 {
            return Err(CursorDecodeError); // v1 tokens are rejected, see QUERYING.md
        }
        Ok(cursor)
    }

    fn keyset(&self) -> Result<(OffsetDateTime, Uuid), CursorDecodeError> {
        let created_at = self
            .k
            .first()
            .and_then(JsonValue::as_str)
            .and_then(|s| OffsetDateTime::parse(s, &time::format_description::well_known::Rfc3339).ok())
            .ok_or(CursorDecodeError)?;
        let id = self
            .k
            .get(1)
            .and_then(JsonValue::as_str)
            .and_then(|s| Uuid::parse_str(s).ok())
            .ok_or(CursorDecodeError)?;
        Ok((created_at, id))
    }
}

#[derive(Debug, sqlx::FromRow)]
pub struct TicketRow {
    pub id: Uuid,
    pub title: String,
    pub created_at: OffsetDateTime,
}

/// Fetch one page for canonical sort `created_at DESC, id DESC`. Returns the
/// raw (over-fetched-by-one) rows in *query* order — forward order for
/// `Next`/no cursor, inverted order for `Prev` — and whether there are more.
pub async fn fetch_ticket_page(
    pool: &sqlx::PgPool,
    cursor: Option<&CursorV2>,
    page_size: i64,
) -> Result<(Vec<TicketRow>, Direction), sqlx::Error> {
    let direction = cursor.map(|c| c.d).unwrap_or(Direction::Next);

    let rows = match (cursor, direction) {
        (None, _) => {
            sqlx::query_as::<_, TicketRow>(
                "SELECT id, title, created_at FROM tickets \
                 ORDER BY created_at DESC, id DESC LIMIT $1",
            )
            .bind(page_size + 1)
            .fetch_all(pool)
            .await?
        }
        (Some(cursor), Direction::Next) => {
            let (created_at, id) = cursor
                .keyset()
                .map_err(|_| sqlx::Error::Protocol("invalid cursor keyset".into()))?;
            sqlx::query_as::<_, TicketRow>(
                "SELECT id, title, created_at FROM tickets \
                 WHERE (created_at, id) < ($2, $3) \
                 ORDER BY created_at DESC, id DESC LIMIT $1",
            )
            .bind(page_size + 1)
            .bind(created_at)
            .bind(id)
            .fetch_all(pool)
            .await?
        }
        (Some(cursor), Direction::Prev) => {
            // Backward: ORDER BY is inverted so LIMIT takes the rows adjacent
            // to the cursor. `trim_and_orient` below re-reverses the trimmed
            // rows so the caller always sees canonical order.
            let (created_at, id) = cursor
                .keyset()
                .map_err(|_| sqlx::Error::Protocol("invalid cursor keyset".into()))?;
            sqlx::query_as::<_, TicketRow>(
                "SELECT id, title, created_at FROM tickets \
                 WHERE (created_at, id) > ($2, $3) \
                 ORDER BY created_at ASC, id ASC LIMIT $1",
            )
            .bind(page_size + 1)
            .bind(created_at)
            .bind(id)
            .fetch_all(pool)
            .await?
        }
    };

    Ok((rows, direction))
}

/// Trims the over-fetched row and, for backward pages, reverses it back into
/// canonical order. Returns `(items, has_more)`; `has_more` alone decides
/// whether a `next_cursor`/`prev_cursor` is emitted (see QUERYING.md — there
/// is no `total_count`).
pub fn trim_and_orient(mut rows: Vec<TicketRow>, page_size: usize, direction: Direction) -> (Vec<TicketRow>, bool) {
    let has_more = rows.len() > page_size;
    rows.truncate(page_size);
    if direction == Direction::Prev {
        rows.reverse();
    }
    (rows, has_more)
}
```

## Idempotency & ETags (server hints)
- Persist `(idempotency_key, request_fingerprint, response_hash, expires_at)`
- On replay with same fingerprint: return stored response + `Idempotency-Replayed: true`
- For writes, compute and return `ETag`; clients send `If-Match` for concurrency

## Timestamps
- Use `time::OffsetDateTime` for timestamp fields.
- **`#[serde(with = "time::serde::rfc3339")]` does NOT guarantee millisecond
  formatting.** The `time` crate's RFC 3339 formatter omits the subsecond
  component entirely when it is zero, emitting `2025-09-01T20:00:00Z` instead
  of `2025-09-01T20:00:00.000Z`. Whole-second timestamps are common (anything
  truncated at insert, anything mocked in a test), so this fires
  intermittently in production, which is worse than always or never.
- Instead, pin a 3-digit-subsecond format description with
  `time::serde::format_description!`, as in the Data Types section above:
  `time::serde::format_description!(iso8601_millis, OffsetDateTime, "[year]-[month]-[day]T[hour]:[minute]:[second].[subsecond digits:3]Z")`.
  Use `#[serde(with = "iso8601_millis")]` for required fields and
  `#[serde(with = "iso8601_millis::option")]` (plus `#[serde(default)]`) for
  optional ones — the macro generates both modules for you.
- `$filter` inputs accept any valid RFC 3339 form; milliseconds are not
  required there. Only *response* timestamps must carry `.SSS`.
- The round-trip test below is part of this guide's own compiled example
  suite (`ci/rust-examples/`) and proves a whole-second timestamp serialises
  with `.000` rather than being silently dropped.

```rust
#[cfg(test)]
mod iso8601_millis_tests {
    use super::iso8601_millis;
    use time::macros::datetime;

    #[derive(serde::Serialize)]
    struct Wrapper {
        #[serde(with = "iso8601_millis")]
        at: time::OffsetDateTime,
    }

    #[test]
    fn whole_second_timestamp_keeps_three_subsecond_digits() {
        let at = datetime!(2025-09-01 20:00:00 UTC);
        let json = serde_json::to_value(Wrapper { at }).unwrap();
        assert_eq!(json["at"], "2025-09-01T20:00:00.000Z");
    }
}
```

## Durations
- Use `std::time::Duration` for duration fields in configuration files.
- To parse human-readable durations (e.g., "5m", "1h 30m", "2d"), wrap
  `Option<Duration>` with the public [`humantime-serde`](https://crates.io/crates/humantime-serde)
  crate: `#[serde(with = "humantime_serde::option", default)]`. The `::option`
  adaptor deserializes into `Option<Duration>` — applying it to a bare
  `Duration` is a type mismatch and does not compile.
- **`#[serde(default)]` on a bare `Duration` silently yields zero** — a
  dangerous default for anything named `timeout` (a zero-second timeout
  either fails every request immediately or, depending on the client, means
  "no timeout," neither of which is what an absent config value should mean).
  This violates PLID-41.03 *Safe Defaults*. Give the field an explicit,
  non-zero default instead, as shown below.
- Usage example in configuration structs:
```rust
use std::time::Duration;

fn default_timeout() -> Option<Duration> {
    Some(Duration::from_secs(30))
}

#[derive(Debug, Serialize, Deserialize)]
pub struct Config {
    #[serde(with = "humantime_serde::option", default = "default_timeout")]
    pub timeout: Option<Duration>,
}
```
- This allows configuration files to use readable formats like `timeout = "30s"` or `retry_interval = "5m"` instead of raw milliseconds or seconds, while an omitted `timeout` resolves to a documented 30-second default rather than zero.

## Norms not yet covered by this guide

This guide is executable, not exhaustive. It does not yet show:

- `$filter` parsing and allowlist enforcement beyond the `ListParams` shape
  (the actual predicate builder and the per-endpoint allowlist check).
- `$select` projection (turning a validated field list into a partial
  `SELECT` / partial serialization).
- `Idempotency-Key` middleware (fingerprinting, replay storage, the
  `409 IDEMPOTENCY_IN_PROGRESS` and `422 IDEMPOTENCY_KEY_REUSED` paths).
- Rate-limit headers (`RateLimit`, `RateLimit-Policy`, `Retry-After`).
- CORS configuration (`tower-http`'s `CorsLayer` wired to this norm set's
  header allowlist).
- Batch endpoints (`:batch`, `:batchUpdate`, `:batchDelete`).
- `ETag` generation for writes and the `If-Match` / `412` concurrency path.
- `Retry-After` on `202`/`429`/`409` responses.

Track these against `E15` in the findings register; contributions welcome.
