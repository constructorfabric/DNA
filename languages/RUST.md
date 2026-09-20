# Rust Backend — Implementation Guide

This file contains Rust-specific guidance and examples.

## Backend Stack & Libraries
- Routing/middleware: `axum`, `tower-http` (CORS, compression, timeouts)
- JSON & validation: `serde`, `validator`
- OpenAPI: `utoipa`, `utoipa-swagger-ui` (optional docs UI)
- Observability: `tracing`, `tracing-subscriber`, `tracing-opentelemetry`
- DB access: `sqlx` or `sea-orm`; use query builders for filters/sorts safely
- IDs & time: `uuid` (v7) or `ulid`; `time` crate for UTC (`OffsetDateTime`)

## OpenAPI Generation
- Annotate handlers with `utoipa::path`
- Export OpenAPI 3.1 JSON at `/v1/openapi.json`
- Validate in CI with an OpenAPI linter

## Data Types
```rust
use serde::{Deserialize, Serialize};
use time::OffsetDateTime;
use utoipa::ToSchema;
use uuid::Uuid; // enable the v7 feature in Cargo.toml

#[derive(Debug, Serialize, Deserialize, ToSchema)]
#[serde(rename_all = "snake_case")]
pub struct Ticket {
    pub id: Uuid,
    pub title: String,
    pub priority: TicketPriority,
    pub status: TicketStatus,
    #[serde(with = "time::serde::rfc3339")]
    pub created_at: OffsetDateTime,
    #[serde(with = "time::serde::rfc3339")]
    pub updated_at: OffsetDateTime,
    #[serde(with = "time::serde::rfc3339::option")]
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
use serde::Serialize;
use utoipa::ToSchema;

/// RFC 9457 Problem Details
#[derive(Debug, Serialize, ToSchema)]
#[serde(rename_all = "snake_case")]
pub struct Problem {
    #[schema(example = "https://api.example.com/errors/validation")]
    pub r#type: String,
    #[schema(example = "Invalid request")]
    pub title: String,
    pub status: u16,
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
```

## axum Handler with utoipa
```rust
use axum::{extract::Query, http::HeaderMap, response::{IntoResponse, Json}};
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use utoipa::{IntoParams, ToSchema};

#[derive(Debug, Deserialize, IntoParams)]
pub struct ListParams {
    // We can capture all query params into a HashMap to handle filters dynamically
    #[serde(flatten)]
    pub filters: HashMap<String, String>,
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

/// List tickets with cursor pagination
#[utoipa::path(
    get,
    path = "/v1/tickets",
    params(ListParams),
    responses(
        (status = 200, description = "List tickets", body = ListResponse<Ticket>),
        (status = 422, description = "Validation error", body = Problem)
    ),
    security(("oauth2" = []))
)]
pub async fn list_tickets(Query(params): Query<ListParams>) -> impl IntoResponse {
    // Example of extracting params from the filters map
    let limit = params.filters.get("limit").and_then(|s| s.parse().ok()).unwrap_or(25);
    let cursor = params.filters.get("cursor").cloned();
    // $filter=status in ('open','in_progress')
    let filter = params.filters.get("$filter").cloned();
    // $orderby=priority desc,created_at asc
    let orderby = params.filters.get("$orderby").cloned();
    // $select=id,title,status,priority
    let select = params.filters.get("$select").cloned();

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

    // Build response with headers
    let mut headers = HeaderMap::new();
    headers.insert("trace_id", "01J...".parse().unwrap());
    (headers, Json(response))
}
```

## Idempotency & ETags (server hints)
- Persist `(idempotency_key, request_fingerprint, response_hash, expires_at)`
- On replay with same fingerprint: return stored response + `Idempotency-Replayed: true`
- For writes, compute and return `ETag`; clients send `If-Match` for concurrency

## Timestamps
- Use `time::OffsetDateTime` for timestamp fields.
- To ensure RFC3339 / ISO-8601 formatting with milliseconds, use `#[serde(with = "time::serde::rfc3339")]` for required fields and `#[serde(with = "time::serde::rfc3339::option")]` for optional ones.

## Durations
- Use `std::time::Duration` for duration fields in configuration files.
- To parse human-readable durations (e.g., "5m", "1h 30m", "2d"), wrap `Duration` in a custom serializer/deserializer using `#[serde(with = "modkit_utils::humantime_serde::option", default)]`.
- Usage example in configuration structs:
```rust
use serde::{Deserialize, Serialize};
use std::time::Duration;

#[derive(Debug, Serialize, Deserialize)]
pub struct Config {
    #[serde(with = "modkit_utils::humantime_serde::option", default)]
    pub timeout: Option<Duration>
}
```
- Note: applying `#[serde(default)]` to a bare `Duration` (rather than `Option<Duration>`) yields a default of **zero**, which is a dangerous default for a timeout field.
- `modkit_utils` is an internal crate; the public equivalent is the [`humantime-serde`](https://crates.io/crates/humantime-serde) crate.
- This allows configuration files to use readable formats like `timeout = "30s"` or `retry_interval = "5m"` instead of raw milliseconds or seconds.
