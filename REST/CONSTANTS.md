# Constants

Every constant below used to be restated in three or four documents, and the restatements had
already drifted from each other (mismatched pagination defaults, inconsistent batch caps). This
document is the single source of truth. Correcting the drifted values fixes the corpus today;
routing every other document through this table instead of restating the literal makes the drift
unrepeatable. **A document that needs a number MUST link here rather than restate it.** Examples
MAY show a concrete value inline for readability, but normative text MUST NOT.

| Name | Value | Scope | Configurable per endpoint? | Defined by |
| --- | --- | --- | --- | --- |
| `DEFAULT_LIMIT` | `25` | Cursor pagination `limit` parameter, applied when the client omits `limit` | No | [QUERYING.md](QUERYING.md) |
| `MIN_LIMIT` | `1` | Cursor pagination `limit` parameter, lower bound | No | [QUERYING.md](QUERYING.md) |
| `MAX_LIMIT` | `200` | Cursor pagination `limit` parameter, upper bound | Yes — an endpoint MAY declare a lower max; it MUST NOT exceed `200` | [QUERYING.md](QUERYING.md) |
| `$select` max fields | `50` | Field projection, fields per request | Yes | [QUERYING.md](QUERYING.md) |
| Queryable indexed fields per endpoint | `10` (recommended cap) | `$filter`/`$orderby` allowlist size | Yes — recommendation, not a hard ceiling | [QUERYING.md](QUERYING.md) |
| Batch max items | `100` | `POST /resources:batch` and sibling batch endpoints, items per request | Yes | [BATCH.md](BATCH.md) |
| Max JSON payload | `1 MB` | Request/response body encoded as `application/json` | Yes | [API.md](API.md) §23 |
| Handler timeout | `30 s` | Synchronous request handling ceiling; longer work MUST use async jobs (API.md §11) | Yes — an endpoint MAY set a lower ceiling; it MUST NOT exceed `30 s` | [API.md](API.md) §23 |
| Idempotency retention — minimum | `1 h` | `Idempotency-Key` cache, default tier | No | [API.md](API.md) §8 |
| Idempotency retention — important | `24 h`–`7 d` | `Idempotency-Key` cache, operations documented per endpoint as "important" | Yes — the endpoint documents the exact value within the range | [API.md](API.md) §8 |
| Idempotency retention — critical | Permanent (DB uniqueness constraint) | `Idempotency-Key` cache, operations documented per endpoint as "critical" | No — permanent is the floor for this tier | [API.md](API.md) §8 |
| Idempotency key length | `1`–`255` characters, printable US-ASCII (`%x21-7E`) | `Idempotency-Key` header value | No | [API.md](API.md) §8 |
| Cursor version | `2` | `v` member of the cursor payload | No | [QUERYING.md](QUERYING.md) |
| Webhook timestamp skew | `±5 min` | `X-Timestamp` header validation window | No | [API.md §12](API.md#12-webhooks-outbound) |

Any summary elsewhere that mentions idempotency retention says "tiered, `1 h` minimum (see
CONSTANTS.md)" rather than a flat duration — a flat number is exactly how the retention rows
above drifted the first time.
