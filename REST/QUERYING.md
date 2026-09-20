## Cursor Pagination Spec

This document defines a consistent, implementation-friendly contract for cursor-based pagination referenced by the API Guidelines.

## Goals

- **Stable ordering**: No duplicates or gaps when paging.
- **Opaque cursors**: Clients never rely on internal fields.
- **Simple client contract**: One optional `cursor` and `limit` param per request.
- **Filter safety**: Cursors are bound to the query/filter they were created from.
- **Extensible**: Versioned cursor payloads for painless future changes.

## Terminology

- **Cursor**: Opaque token representing a position in a sorted result set **and a direction of travel from it**.
- **Page**: Up to `limit` items returned for a given cursor.
- **Canonical sort**: Endpoint-defined, immutable ordering (includes a unique tiebreaker).
- **Canonical order**: The order the canonical sort produces. Responses are ALWAYS serialised in canonical order, whichever direction the client paged in.

## Request

Query parameters every paginated endpoint MUST accept:

- `limit` (integer): Number of items to return. `DEFAULT_LIMIT`, `MIN_LIMIT` and `MAX_LIMIT` are defined once in [CONSTANTS.md](CONSTANTS.md); endpoints MAY document a lower maximum. A `limit` outside the range is REJECTED, never clamped — see [Validation Rules](#validation-rules).
- `cursor` (string, optional): Opaque token returned by a previous response. A cursor identifies **a position and a direction**; the direction of travel is carried inside the token (member `d`), not inferred from the parameter name. Passing `next_cursor` returns the page after the current one; passing `prev_cursor` returns the page before it.

OData parameters for client-defined filtering and sorting (RECOMMENDED):

A **subset of OData syntax** is employed for filtering and sorting, offering familiar, standardized query capabilities while ensuring simplicity in implementation.

- `$filter` (string, optional): OData-style filter expression. Examples:
  - `price gt 10 and startswith(name,'Pro')`
  - `status in ('paid','shipped') and created_at ge 2025-01-01T00:00:00Z`
  - Supported operators: `eq`, `ne`, `gt`, `ge`, `lt`, `le`, `and`, `or`, `not`, `in` (set membership), functions `startswith`, `endswith`, `contains`. Strings use single quotes; timestamps are RFC 3339 UTC.
  - `$filter` timestamps are RFC 3339 **inputs** and accept any valid RFC 3339 form. The mandatory `.SSS` millisecond precision in [API.md](API.md) §13 governs **response** timestamps only.
- `$orderby` (string, optional): OData-style order-by list. Examples:
  - `created_at desc, id desc`
  - MUST include a unique tiebreaker (typically `id`) last for stable pagination; if omitted, the server appends `id` automatically.

Notes:

- Endpoints MUST document their canonical sort and whether it is ascending or descending.
- Only indexed fields MAY be used in `$filter` and `$orderby`.
- If an endpoint supports client-selectable sort, filters or projection, the cursor MUST encode and validate all three (`s`, `f`, `p`); otherwise requests with mismatched params MUST be rejected — see [Validation Rules](#validation-rules).

### Request Phases

- First request (no `cursor`):
  - Client MAY supply `limit`, `$orderby`, `$filter` and `$select`.
  - Server validates `$orderby` tokens (see [Ordering Fields](#ordering-fields)) and ensures a unique tiebreaker is last (or appends `id`).
  - Server applies `$filter`, `$orderby` and `$select`, returns the page, and mints cursors encoding the effective sort `s`, the normalized filter hash `f`, the normalized projection hash `p`, and the direction `d`.
- Subsequent requests (with `cursor`):
  - The cursor fully defines ordering (`s`), filters (`f`), projection (`p`) and direction (`d`).
  - `$orderby`, `$filter` and `$select` MAY be resent, but MUST agree with the cursor. Disagreement is rejected, never ignored — see [Validation Rules](#validation-rules).

## Response

Return a consistent envelope:

```json
{
  "items": [ ],
  "page_info": {
    "next_cursor": "<opaque>",
    "prev_cursor": "<opaque>",
    "limit": 25
  }
}
```

Rules:

- `items` are in the endpoint's **canonical sort order**, whichever direction the client navigated in. A backward query is executed with an inverted `ORDER BY` and the result set is re-reversed before serialisation, so the response is always canonical — see [Backward Navigation](#backward-navigation).
- `next_cursor` points to the position immediately after the last item in `items` and is OMITTED when there is no next page.
- `prev_cursor` points to the position immediately before the first item in `items` and is OMITTED when there is no previous page.
- **The presence of `next_cursor` is the "has more pages" signal.** That is what the over-fetch-by-one in the [Implementation Recipe](#implementation-recipe-sqlorm) is for: fetch `limit + 1` rows, and if the extra row exists, emit `next_cursor`. Clients MUST NOT infer "has more" from `items.length == limit`.
- `page_info` MUST NOT include `total_count`. See [Counting](#counting) for the sanctioned alternative.

### Counting

Counting a filtered set is a different operation from paging it, with a different cost profile, so it gets its own endpoint rather than a member of `page_info`:

```http
GET /v1/messages:count?$filter=active eq true
```

```json
{ "count": 1483, "exact": true }
```

- `count` (integer): the number of items matching `$filter`.
- `exact` (boolean): `false` when the value is an estimate. Endpoints that estimate MUST document the threshold above which they stop counting exactly.
- The endpoint accepts `$filter` only. `limit`, `cursor`, `$orderby` and `$select` are not applicable and MUST be rejected with `400 INVALID_QUERY`.

Endpoints are not required to offer `:count`. Those that do not MUST say so, so consumers do not invent a local substitute.

## Canonical Sort Requirements

- MUST be total and stable: combine the primary sort key with a unique tiebreaker (e.g., `created_at DESC, id DESC`).
- The unique tiebreaker MUST be monotonic with respect to insertion order or at least unique. UUIDv7 is REQUIRED for resource identifiers (see [API.md](API.md) §3); its lexicographic order aligns with creation time.
- Example canonical sorts:
  - Timelines: `created_at DESC, id DESC`
  - Oldest-first logs: `created_at ASC, id ASC`

## Ordering Fields

Define ordering using standardized field tokens. By default, only `created_at` and `id` are allowed for ordering. Specific APIs MAY add more ordering fields if they are indexed and documented in the endpoint's allowlist.

- `created_at` (timestamp, RFC 3339/UTC)
  - RECOMMENDED primary key for feeds and most lists.
  - MUST be non-null and represent creation time.
  - Comparison: timestamp value; for DESC, newer first.
- `id` (string, UUIDv7)
  - REQUIRED unique tiebreaker in all canonical sorts.
  - Comparison: lexicographic on the canonical UUID string. With UUIDv7, lexicographic order preserves creation-time ordering.
  - Format: lowercase hyphenated UUIDv7 string.

> Additional ordering fields MAY be defined per endpoint. Each MUST be indexed, documented in the endpoint's allowlist, and accompanied by explicit comparison semantics. Fields whose display value is not their sort value (an enum ranked by severity, for example) MUST document the sort value, because it is the sort value that the cursor carries in `k`.

Field comparison semantics:

- Strings: compare using defined collation; default is case-insensitive NFKC with `en-US` unless the endpoint specifies otherwise.
- Timestamps: compare by instant in UTC.
- Numbers: IEEE-754 comparisons; NaN not allowed; nulls not allowed in ordering fields.

Allowed `s` tokens (comma-separated, each with an explicit `+`/`-` direction prefix): `created_at`, `id`.

- Endpoints MAY introduce additional domain-specific tokens if documented; include them verbatim in `s` and define their comparison semantics. All tokens MUST correspond to indexed fields.

## Indexed Fields & Allowed Parameters

- Filtering and ordering are allowed only on fields backed by suitable database indexes.
  - For string functions (e.g., `startswith`, `contains`), enable only when supported by an index (prefix, trigram, full-text); otherwise reject the filter.
- The set of queryable indexed fields MUST be limited. RECOMMENDED cap per endpoint: see [CONSTANTS.md](CONSTANTS.md).
- Each endpoint MUST publish an allowlist of:
  - `$filter` fields (and supported operators per field), and
  - `$orderby` fields (with allowed directions),
  in the generated API spec.
  - Suggested OpenAPI vendor extensions:

```yaml
x-odata-filter:
  allowedFields:
    created_at: [ge, gt, le, lt, eq]
    id: [eq, in]

x-odata-orderby:
  allowedFields:
    - created_at desc
    - created_at asc
    - id asc
```

## OpenAPI Contract Requirements

Generated OpenAPI MUST explicitly document the allowed filter and order parameters per endpoint.

- Parameters:
  - `$filter` (query, string): OData filter expression restricted to the endpoint's allowlisted, indexed fields and operators.
  - `$orderby` (query, string): Comma-separated OData ordering, restricted to allowlisted, indexed fields and directions.
- Include the allowlists in vendor extensions for machine-readability, and reference them in parameter descriptions.

Example OpenAPI fragment:

```yaml
components:
  parameters:
    FilterParam:
      name: $filter
      in: query
      required: false
      schema:
        type: string
      description: |
        OData filter over allowlisted indexed fields. See x-odata-filter.allowedFields.
    OrderByParam:
      name: $orderby
      in: query
      required: false
      schema:
        type: string
      example: created_at desc, id desc
      description: |
        OData order-by over allowlisted indexed fields. See x-odata-orderby.allowedFields.

paths:
  /v1/items:
    get:
      parameters:
        - $ref: '#/components/parameters/FilterParam'
        - $ref: '#/components/parameters/OrderByParam'
      x-odata-filter:
        allowedFields:
          created_at: [ge, gt, le, lt, eq]
          id: [eq, in]
      x-odata-orderby:
        allowedFields:
          - created_at desc
          - created_at asc
          - id asc
```

## Cursor Format (Opaque, Versioned)

- Base64URL (no padding) encoded compact JSON object (no insignificant whitespace).
- Current version: `v = 2`.

```json
{
  "v": 2,
  "k": ["2025-09-14T12:34:56.789Z", "018f6c9e-1a2b-7c3d-9e4f-5a6b7c8d9e0f"],
  "s": "-created_at,-id",
  "d": "next",
  "f": "96a792a01275",
  "p": null
}
```

| Member | Type | Required | Meaning |
| --- | --- | --- | --- |
| `v` | integer | yes | Cursor format version. Currently `2`. |
| `k` | array | yes | The raw comparison values of the anchor row, one per token in `s`, in the same order. |
| `s` | string | yes | Effective sort, as comma-separated tokens each carrying an explicit `+` (ASC) or `-` (DESC) prefix, e.g. `-created_at,-id` or `-priority,+created_at,+id`. |
| `d` | string | yes | Direction of travel from the anchor: `"next"` or `"prev"`. |
| `f` | string \| null | yes | Hash of the normalized `$filter`; `null` when no `$filter` was supplied. |
| `p` | string \| null | yes | Hash of the normalized `$select`; `null` for the default projection. |

Guidelines:

- `k` carries the values needed for comparison in the database (e.g., an RFC 3339 timestamp string and an id string). When multiple sort keys are used, `k` MUST include a value for each, in `s` order.
- `d` is set when the cursor is minted: `next_cursor` is minted with `"next"`, `prev_cursor` with `"prev"`. Because both are sent back in the same `cursor` parameter, `d` is the only thing that tells the server whether to look forward or backward. Without it, backward pagination is not implementable.
- Direction lives in `s` per token; there is no separate `o` member. `o` existed in `v = 1`, was redundant with `s`, and could not express a mixed-direction sort — that is why it was removed.
- Use Base64URL without padding so tokens are URL-safe.
- Treat the token as completely opaque to clients; they MUST NOT parse it.

### Normalization and hashing

`f` and `p` MUST be computed as `lowercase-hex(sha256(normalized_string))[0:12]`, so that any two implementations of this spec produce the same cursor for the same query.

- `$select` normalization: split on `,`, trim each field, sort ascending, join with `,`.
- `$filter` normalization: collapse runs of whitespace to a single space, trim, lowercase operator and function names, and sort the members of every `in (...)` set ascending.

Example: `$filter=active eq true` normalizes to `active eq true`, whose hash is `96a792a01275`.

## Validation Rules

- If `cursor` is present, decode and validate:
  - Known `v`. A `v = 1` token is rejected — see [Versioning](#versioning).
  - `s` matches the endpoint's canonical sort or an allowlisted client-selected sort.
  - `d` is `"next"` or `"prev"`.
  - `k` has exactly one value per token in `s`.
- On any structural decoding failure, return `400` with `code: "INVALID_CURSOR"`.
- When a cursor is present, the query parameters it binds MUST agree with it, and disagreement is **rejected, never ignored**:
  - `$orderby` MUST be absent or normalize to the cursor's `s`; otherwise `400` with `code: "ORDER_MISMATCH"`.
  - `$filter` MUST be absent or hash to the cursor's `f`; otherwise `400` with `code: "FILTER_MISMATCH"`.
  - `$select` MUST be absent or hash to the cursor's `p`; otherwise `400` with `code: "FIELD_SELECTION_MISMATCH"`.
- If `limit` is outside `[MIN_LIMIT, MAX_LIMIT]`, return `422` with `code: "INVALID_LIMIT"`. Do not clamp: clamping silently returns a different page size than the client asked for, and the client cannot tell.
- Validate that all fields referenced in `$filter` and `$orderby` belong to the endpoint's allowlist of indexed fields; otherwise return `400` with `code: "UNSUPPORTED_FILTER_FIELD"` or `code: "UNSUPPORTED_ORDERBY_FIELD"`.
- Reject unknown query parameters with `400` and `code: "INVALID_QUERY"` rather than silently ignoring them.

The 400-vs-422 split follows the decision rule in [STATUS_CODES.md](STATUS_CODES.md): 400 for unparseable input or an identifier outside the allowlist, 422 for a parseable request whose value violates a documented constraint. The three `*_MISMATCH` codes are 400 by deliberate exception — the fault is in how the request was assembled, since it contradicts a token it carries itself.

## Implementation Recipe (SQL/ORM)

Assume canonical sort `created_at DESC, id DESC`, so `s = "-created_at,-id"`.

1. Validate `limit`. If present and outside `[MIN_LIMIT, MAX_LIMIT]`, return `422 INVALID_LIMIT`. Otherwise `page_size = limit ?? DEFAULT_LIMIT`.
2. If `cursor` is provided, decode it to `(k, s, d, f, p)` and run the validation rules above. Otherwise `d = "next"` and the cursor predicate is omitted.
3. Build the cursor predicate. For each token in `s`, the comparison operator is determined by the token's direction **and** by `d`:
   - `d = "next"`: a `-` token compares `<`, a `+` token compares `>`.
   - `d = "prev"`: every comparison is inverted — a `-` token compares `>`, a `+` token compares `<`.
4. Build the `ORDER BY`:
   - `d = "next"`: the canonical sort, unchanged.
   - `d = "prev"`: the canonical sort **with every direction inverted**. This is what makes `LIMIT` take the rows adjacent to the cursor rather than the rows at the far end of the result set.
5. Apply filters first, then the cursor predicate.
6. Fetch `page_size + 1` rows.
7. `has_more = rows.length > page_size`; `items = rows.slice(0, page_size)`.
8. If `d = "prev"`, **reverse `items` in memory**. The response is now in canonical order regardless of direction.
9. Compute cursors from the trimmed, canonically ordered `items`:
   - `next_cursor` from the **last** item, minted with `d = "next"`.
   - `prev_cursor` from the **first** item, minted with `d = "prev"`.
   - Emit `next_cursor` when there is a next page, `prev_cursor` when there is a previous page. Under `d = "next"`, `has_more` decides `next_cursor` and the presence of an incoming cursor decides `prev_cursor`; under `d = "prev"` the two swap.
10. Serialise `items` and `page_info`. Omit any cursor that does not apply; do not emit `null`.

### Why the backward query inverts `ORDER BY`

Keeping the canonical `ORDER BY` for a backward query is the single most common way to get keyset pagination wrong, and it is wrong in a way that only shows up from page 3 onward.

Take nine items A (newest) … I (oldest), canonical sort `created_at DESC`, `limit = 3`. The client is on page 3, `[G, H, I]`, and pages back.

- **Wrong**: `WHERE created_at > G ORDER BY created_at DESC LIMIT 3`. The predicate selects the six rows A–F; `ORDER BY DESC` puts A first; `LIMIT 3` takes `[A, B, C]` — **page 1, not page 2**. The bug is invisible when paging back from page 2, because there page 1 and "the page before this one" are the same thing.
- **Right**: `WHERE created_at > G ORDER BY created_at ASC LIMIT 3`. The predicate selects A–F; `ORDER BY ASC` puts F first; `LIMIT 3` takes `[F, E, D]` — the rows adjacent to the cursor. Reverse in memory to get `[D, E, F]`, which is page 2, serialised canonically.

### Complete Pagination Examples: All 4 Scenarios

All combinations of forward/backward navigation with ascending/descending canonical ordering. `:has_cursor IS FALSE` covers the first page, where no cursor predicate applies.

#### Scenario 1: Forward navigation, DESC canonical sort

**Canonical sort**: `created_at desc, id desc` — `s = "-created_at,-id"`, cursor `d = "next"`

```sql
-- Given :page_size_plus_one, :cursor_created_at, :cursor_id
WHERE (
  :has_cursor IS FALSE
  OR created_at < :cursor_created_at
  OR (created_at = :cursor_created_at AND id < :cursor_id)
)
ORDER BY created_at DESC, id DESC        -- canonical
LIMIT :page_size_plus_one
```

No in-memory reversal: the query order is already canonical.

#### Scenario 2: Backward navigation, DESC canonical sort

**Canonical sort**: `created_at desc, id desc` — `s = "-created_at,-id"`, cursor `d = "prev"`

```sql
-- Given :page_size_plus_one, :cursor_created_at, :cursor_id
WHERE (
  created_at > :cursor_created_at
  OR (created_at = :cursor_created_at AND id > :cursor_id)
)
ORDER BY created_at ASC, id ASC          -- INVERTED
LIMIT :page_size_plus_one
```

Then `items = rows.slice(0, page_size).reverse()` so the response is canonical (`created_at DESC`).

#### Scenario 3: Forward navigation, ASC canonical sort

**Canonical sort**: `created_at asc, id asc` — `s = "+created_at,+id"`, cursor `d = "next"`

```sql
-- Given :page_size_plus_one, :cursor_created_at, :cursor_id
WHERE (
  :has_cursor IS FALSE
  OR created_at > :cursor_created_at
  OR (created_at = :cursor_created_at AND id > :cursor_id)
)
ORDER BY created_at ASC, id ASC          -- canonical
LIMIT :page_size_plus_one
```

No in-memory reversal.

#### Scenario 4: Backward navigation, ASC canonical sort

**Canonical sort**: `created_at asc, id asc` — `s = "+created_at,+id"`, cursor `d = "prev"`

```sql
-- Given :page_size_plus_one, :cursor_created_at, :cursor_id
WHERE (
  created_at < :cursor_created_at
  OR (created_at = :cursor_created_at AND id < :cursor_id)
)
ORDER BY created_at DESC, id DESC        -- INVERTED
LIMIT :page_size_plus_one
```

Then `items = rows.slice(0, page_size).reverse()` so the response is canonical (`created_at ASC`).

#### Mixed-Direction Sort Example

For `$orderby=score desc, created_at asc, id asc` — `s = "-score,+created_at,+id"`.

**Forward** (`d = "next"`): `-` tokens compare `<`, `+` tokens compare `>`.

```sql
-- Given :page_size_plus_one, :cursor_score, :cursor_created_at, :cursor_id
WHERE (
  :has_cursor IS FALSE
  OR score < :cursor_score
  OR (score = :cursor_score AND created_at > :cursor_created_at)
  OR (score = :cursor_score AND created_at = :cursor_created_at AND id > :cursor_id)
)
ORDER BY score DESC, created_at ASC, id ASC        -- canonical
LIMIT :page_size_plus_one
```

**Backward** (`d = "prev"`): every comparison inverts, and every `ORDER BY` direction inverts.

```sql
-- Given :page_size_plus_one, :cursor_score, :cursor_created_at, :cursor_id
WHERE (
  score > :cursor_score
  OR (score = :cursor_score AND created_at < :cursor_created_at)
  OR (score = :cursor_score AND created_at = :cursor_created_at AND id < :cursor_id)
)
ORDER BY score ASC, created_at DESC, id DESC       -- INVERTED
LIMIT :page_size_plus_one
```

Then `items = rows.slice(0, page_size).reverse()`.

Notes:

- Many databases support mixed-direction indexes; verify support for your engine. The inverted `ORDER BY` of a backward query needs the same index read in the opposite direction, which every mainstream engine supports.
- This OR-chain predicate matches the index order and remains sargable.

### Key Principles

1. **Forward** means "the next page in the canonical sort direction"; **backward** means "the previous page in the canonical sort direction".
2. The direction of travel is carried in the cursor (`d`), not in the parameter name and not in the sort.
3. **The backward query inverts `ORDER BY`.** This is what makes `LIMIT` select the rows adjacent to the cursor instead of the rows at the far end of the result set.
4. The `WHERE` comparison operators are inverted for backward navigation, together with the `ORDER BY`. Inverting one without the other is the defect described above.
5. **The response is always canonical.** A backward result set is re-reversed in memory before serialisation, so `items` never arrives reversed at the client.

## Examples

### Request

First page:

```http
GET /v1/messages?limit=25&$filter=active eq true&$orderby=created_at desc, id desc
```

Subsequent page, using a `next_cursor` from an earlier response. The cursor already carries the sort, the filter hash and the direction, so resending `$filter`/`$orderby` is optional:

```http
GET /v1/messages?limit=25&cursor=eyJ2IjoyLCJrIjpbIjIwMjUtMDktMTRUMTI6MzQ6NTcuNTAwWiIsIjAxOGY2YzllLTNkNGUtN2Y1YS04YjZjLTdkOGU5ZjBhMWIyYyJdLCJzIjoiLWNyZWF0ZWRfYXQsLWlkIiwiZCI6Im5leHQiLCJmIjoiOTZhNzkyYTAxMjc1IiwicCI6bnVsbH0
```

That token decodes to:

```json
{"v":2,"k":["2025-09-14T12:34:57.500Z","018f6c9e-3d4e-7f5a-8b6c-7d8e9f0a1b2c"],"s":"-created_at,-id","d":"next","f":"96a792a01275","p":null}
```

### Response

```json
{
  "items": [
    { "id": "018f6c9e-2c3b-7b1a-8f4a-9c3d2b1a0e5f", "created_at": "2025-09-14T12:34:57.100Z", "text": "..." },
    { "id": "018f6c9e-1a2b-7c3d-9e4f-5a6b7c8d9e0f", "created_at": "2025-09-14T12:34:56.789Z", "text": "..." }
  ],
  "page_info": {
    "next_cursor": "eyJ2IjoyLCJrIjpbIjIwMjUtMDktMTRUMTI6MzQ6NTYuNzg5WiIsIjAxOGY2YzllLTFhMmItN2MzZC05ZTRmLTVhNmI3YzhkOWUwZiJdLCJzIjoiLWNyZWF0ZWRfYXQsLWlkIiwiZCI6Im5leHQiLCJmIjoiOTZhNzkyYTAxMjc1IiwicCI6bnVsbH0",
    "prev_cursor": "eyJ2IjoyLCJrIjpbIjIwMjUtMDktMTRUMTI6MzQ6NTcuMTAwWiIsIjAxOGY2YzllLTJjM2ItN2IxYS04ZjRhLTljM2QyYjFhMGU1ZiJdLCJzIjoiLWNyZWF0ZWRfYXQsLWlkIiwiZCI6InByZXYiLCJmIjoiOTZhNzkyYTAxMjc1IiwicCI6bnVsbH0",
    "limit": 25
  }
}
```

`next_cursor` decodes to the **last** item's key with `d: "next"`; `prev_cursor` decodes to the **first** item's key with `d: "prev"`:

```json
{"v":2,"k":["2025-09-14T12:34:56.789Z","018f6c9e-1a2b-7c3d-9e4f-5a6b7c8d9e0f"],"s":"-created_at,-id","d":"next","f":"96a792a01275","p":null}
{"v":2,"k":["2025-09-14T12:34:57.100Z","018f6c9e-2c3b-7b1a-8f4a-9c3d2b1a0e5f"],"s":"-created_at,-id","d":"prev","f":"96a792a01275","p":null}
```

Both cursors are reproducible from the response above: take the anchor item's key values, the effective sort, the direction, and the hash of the normalized `$filter` (`sha256("active eq true")[0:12] = 96a792a01275`), serialise compactly, and Base64URL-encode without padding.

## Edge Cases & Guarantees

- Returning fewer than `limit` items is allowed (e.g., last page).
- `next_cursor` is omitted when there is no further item; `prev_cursor` is omitted on the very first page. Omit the member; do not emit `null`.
- Inserts/deletes during pagination:
  - The strictly monotonic tuple comparison `(primary, …, tiebreaker)` prevents duplicates and minimizes gaps.
  - Absolute consistency is not guaranteed without snapshots; this is acceptable for feed-like listings.
- Cursors are stateless and MAY be reused; servers MAY expire old formats by rejecting an outdated `v`.

## Do's and Don'ts

- **Do** include a unique tiebreaker in the sort.
- **Do** over-fetch by one to compute the existence of a next page, and connect that to emitting `next_cursor`.
- **Do** validate that filters, sort and projection match what the cursor encodes, and reject on mismatch.
- **Do** invert both the `WHERE` comparisons and the `ORDER BY` for a backward query, then re-reverse the trimmed rows.
- **Don't** expose database IDs or raw fields as cursors; keep them opaque and versioned.
- **Don't** provide `total_count` in cursor pagination; use the `:count` endpoint.
- **Don't** serialise items in reversed order for backward navigation. The *query* is reversed; the *response* is canonical.
- **Don't** clamp an out-of-range `limit`. Reject it.

## Backward Navigation

Clients navigate backward by sending `prev_cursor` as the `cursor` value in a new request. Nothing else changes: the same parameter, the same endpoint, the same response shape.

Server-side, the `d: "prev"` inside the token selects the inverted query described in the [Implementation Recipe](#implementation-recipe-sqlorm) — inverted comparisons, inverted `ORDER BY`, and an in-memory reversal of the trimmed rows. The client never sees any of that: `items` arrives in canonical order, and the returned `next_cursor`/`prev_cursor` pair is computed from the page it just received.

## Versioning

- Current version is `v = 2`.
- `v = 1` tokens are rejected with `400 INVALID_CURSOR`. Version 1 lacked `d` (making backward navigation unimplementable) and `p` (making the projection-lock rule unimplementable), and carried a redundant `o` member.
- On future breaking changes to cursor content or comparison semantics, bump `v` and reject older tokens with `INVALID_CURSOR`.

---

# Field Projection with `$select`

## Overview

Sparse field selection via the OData-style `$select` query parameter. Returns only requested fields to reduce payload size.

**Syntax**: `$select=field1,field2,field3` (comma-separated, no whitespace, case-sensitive)

**Examples**:

```http
GET /v1/tickets/018f6c9e-2c3b-7b1a-8f4a-9c3d2b1a0e5f?$select=id,title,status,priority
GET /v1/tickets?$filter=status eq 'open'&$orderby=priority desc&$select=id,title,status
```

**Relation expansion** is not supported. `$expand` is the destination for it and has not shipped; until it does, clients fetch related resources in separate requests. There is deliberately no interim mechanism — see [API.md](API.md) §23.

## Default Projection

When `$select` is omitted, servers return a **default projection**:

- **Includes**: Common fields (`id`, `type`), core business fields (`title`, `status`), timestamps, small reference IDs
- **Excludes**: Large text fields, binary data, sensitive fields, expensive computed fields

The default projection MUST be documented per resource in OpenAPI using the `x-odata-select` vendor extension.

## Allowlisting & Security

- Only **allowlisted fields** MAY appear in `$select` → `400 INVALID_FIELD` if not allowed
- **Max fields per request**: see [CONSTANTS.md](CONSTANTS.md) → `422 TOO_MANY_FIELDS` if exceeded
- Authorization via allowlist definition (at design time), not runtime checks

## Response Format

**Request**:

```http
GET /v1/tickets?limit=2&$select=id,title,status
```

**Response** (200 OK) — only requested fields included:

```json
{
  "items": [
    { "id": "018f6c9e-5f60-7b7c-8d8e-9f0a1b2c3d4e", "title": "Database timeout", "status": "open" },
    { "id": "018f6c9e-4e5f-7a6b-8c7d-9e0f1a2b3c4d", "title": "Login error", "status": "in_progress" }
  ],
  "page_info": {
    "limit": 2,
    "next_cursor": "eyJ2IjoyLCJrIjpbIjIwMjUtMDktMTJUMDg6MTU6MjIuNDAwWiIsIjAxOGY2YzllLTRlNWYtN2E2Yi04YzdkLTllMGYxYTJiM2M0ZCJdLCJzIjoiLWNyZWF0ZWRfYXQsLWlkIiwiZCI6Im5leHQiLCJmIjpudWxsLCJwIjoiMWQ3NTU0YjZkM2IzIn0"
  }
}
```

The cursor decodes to:

```json
{"v":2,"k":["2025-09-12T08:15:22.400Z","018f6c9e-4e5f-7a6b-8c7d-9e0f1a2b3c4d"],"s":"-created_at,-id","d":"next","f":null,"p":"1d7554b6d3b3"}
```

Note that `p` is present even though `created_at` is not in the projection: cursor fields are always selected internally (see [Implementation Notes](#implementation-notes)). `p` is `sha256("id,status,title")[0:12]` — the requested fields, sorted. `f` is `null` because no `$filter` was sent. `prev_cursor` is omitted because this is the first page.

## Interaction with Pagination

Cursors encode `$filter` (as `f`), `$orderby` (as `s`) **and `$select` (as `p`)** to ensure a consistent response shape across pages.

**Field selection is locked per pagination session.** Sending a `$select` that does not hash to the cursor's `p` returns `400 FIELD_SELECTION_MISMATCH`. To use different fields, start a new pagination session without a cursor.

## Error Handling

All errors return RFC 9457 Problem Details, including the REQUIRED top-level `code` member. See [STATUS_CODES.md](STATUS_CODES.md) for the code registry.

**`INVALID_FIELD` (400)**: Requested field not in the allowlist — an identifier outside the allowlist, hence 400. Returns `invalid_fields` array and `allowed_fields` array.

**`TOO_MANY_FIELDS` (422)**: Exceeded the max field limit. The request parses and every field is valid; only the count violates a documented bound, hence 422. Returns `max_fields` integer and `requested_fields` integer.

**`FIELD_SELECTION_MISMATCH` (400)**: Cannot change `$select` during pagination. Returns `cursor_select` string and `request_select` string.

## OpenAPI Integration

Document field projection using the `x-odata-select` vendor extension.

### Vendor Extension

```yaml
x-odata-select:
  defaultFields: [id, title, status, priority, created_at, updated_at]
  allowedFields: [id, title, description, status, priority, created_at, updated_at, assignee_id, reporter_id]
  maxFields: 50
```

Field types are defined in the resource schema; `x-odata-select` only specifies which fields are selectable.

## Code Examples

**Get ticket with specific fields**:

```bash
curl -sS \
  -H "Authorization: Bearer $TOKEN" \
  "https://api.example.com/v1/tickets/018f6c9e-2c3b-7b1a-8f4a-9c3d2b1a0e5f?\$select=id,title,status,priority"
```

**Combine with filtering, sorting, and pagination**:

```bash
curl -sS \
  -H "Authorization: Bearer $TOKEN" \
  "https://api.example.com/v1/tickets?limit=25&\$filter=status eq 'open'&\$orderby=priority desc&\$select=id,title,priority,status"
```

## Implementation Notes

**Server validation**: Parse comma-separated fields, validate against the allowlist, check the field count limit, and return the status codes above. Reject rather than silently truncate.

**Database**: Use SQL column pruning (`SELECT field1, field2`, not `SELECT *`). Always select the primary key and every field named in the cursor's `s` internally, even when `$select` omits them — the cursor cannot be minted otherwise.

**Security**: Enforce allowlists (never arbitrary field selection), exclude sensitive fields at design time, and log selection patterns.
