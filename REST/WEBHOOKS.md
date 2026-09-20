# Webhooks (Outbound)

This document is the complete specification for [API.md](API.md) §12, which keeps only a quick
reference and delegates here, matching how §5/§18/§19 delegate to their own documents.

## Event Shape

```json
{
  "id": "018f6c9e-2c3b-7b1a-8f4a-9c3d2b1a0e5f",
  "event_type": "ticket.created",
  "created_at": "2025-09-14T12:34:56.789Z",
  "data": {
    "id": "018f6c9e-1a2b-7c3d-9e4f-5a6b7c8d9e0f",
    "status": "open"
  }
}
```

- **`id`** is the event's own identifier — a UUIDv7 (D10), unique per delivery attempt group. It
  is carried on the wire a second time in the `X-Event-Id` header (below) so receivers can dedupe
  without parsing the body first.
- API.md's earlier text called this field `id` in one place and `event_id` in another; **`id`**
  is the field name inside the event payload, and **`X-Event-Id`** is the header name. There is no
  third spelling. The event's own *kind* is a separate field, **`event_type`** (below), and is not
  to be confused with the identifier.
- **`event_type`** follows `<resource>.<action>`, e.g. `ticket.created`, `ticket.updated`,
  `ticket.deleted`. `<action>` is a fixed small vocabulary per resource; new actions are additive
  (non-breaking) and MUST be documented before first delivery.
- **`data`** is the affected resource, or the minimal subset of it needed to act on the event; its
  shape is versioned independently per the next section.

## Event Versioning

- Event payload shape changes follow the same non-breaking/breaking split as API.md §22: adding
  optional fields to `data` is non-breaking; removing a field, changing a type, or changing
  `event_type`'s meaning is breaking.
- A breaking change to an event's `data` shape ships as a new `event_type` value (e.g.
  `ticket.created` → `ticket.created.v2`) rather than mutating the existing one silently —
  subscribers already parsing `ticket.created` MUST NOT have their contract change under them.

## Delivery

- `POST` the event as `application/json` to the subscriber's registered URL.
- Delivery is **NOT ordered**. Two events for the same resource MAY arrive out of order, MAY be
  retried independently, and MAY be delivered concurrently. Receivers MUST NOT assume that
  arrival order matches `created_at` order and MUST use `created_at` (and, where the resource
  exposes one, a monotonic version/sequence field) to decide whether an incoming event is newer
  than the receiver's current state before applying it.

## Signing and Verifying

The signature base string is the single most important piece of this document — without an exact
byte-for-byte definition, no receiver can verify anything.

**Construction**: the signed payload is the UTF-8 string

```
v1:<timestamp>:<raw request body>
```

where `<timestamp>` is the exact value sent in `X-Timestamp` (decimal Unix seconds, as a string,
no leading zeros) and `<raw request body>` is the exact bytes of the HTTP request body — not a
re-serialization of it. The three parts are joined with `:`. The digest is
`hex(HMAC-SHA256(secret, signed_payload))`, lowercase hex, no separators.

**Headers**:

- `X-Timestamp: <unix-seconds>` — decimal string, e.g. `1757861700`.
- `X-Signature: v1=<hex-digest>` — the `v1=` prefix is the scheme version (see Rotation below).

### Worked Example

Fixed inputs, so a receiver implementation can be tested against this exact vector:

- Secret: `whsec_5f6a1c2d3e4f5061728394a5b6c7d8e9`
- `X-Timestamp`: `1757861700`
- Raw body:
  ```
  {"id":"018f6c9e-2c3b-7b1a-8f4a-9c3d2b1a0e5f","event_type":"ticket.created","created_at":"2025-09-14T12:34:56.789Z","data":{"id":"018f6c9e-1a2b-7c3d-9e4f-5a6b7c8d9e0f","status":"open"}}
  ```
- Signed payload (`v1:<timestamp>:<raw body>`):
  ```
  v1:1757861700:{"id":"018f6c9e-2c3b-7b1a-8f4a-9c3d2b1a0e5f","event_type":"ticket.created","created_at":"2025-09-14T12:34:56.789Z","data":{"id":"018f6c9e-1a2b-7c3d-9e4f-5a6b7c8d9e0f","status":"open"}}
  ```
- `X-Signature`:
  ```
  v1=22228fe85ed25f0463daace3184c7dde941e7a9eaa745bca14f56e91b6cf0d77
  ```

Computed with `hmac.new(secret.encode(), signed_payload.encode(), hashlib.sha256).hexdigest()`.

**Verification steps** a receiver MUST follow, in order:

1. Reject if `X-Timestamp` is more than **±5 minutes** (see [CONSTANTS.md](CONSTANTS.md)) from
   the receiver's current time — this bounds replay of a captured request.
2. Recompute the signed payload from the received `X-Timestamp` and the raw request body exactly
   as received (before any JSON parsing or re-serialization).
3. Recompute the HMAC-SHA256 digest with each currently-active secret (see Rotation) and compare
   using a constant-time comparison. Accept if any active secret matches.
4. Reject with no further processing if no active secret produces a match.

### Scheme Versioning and Key Rotation

- The `v1=` prefix on `X-Signature` is the signature scheme version. A future scheme bump ships
  as `v2=` alongside `v1=` (space-separated in the header value) during the transition, so
  receivers pinned to `v1` keep working.
- Secret rotation: the subscription MAY have **two active secrets** at once. During rotation, the
  server signs every delivery with the newest secret only, but a receiver verifies against all of
  its currently-known active secrets, so it can adopt the new secret before the old one is
  retired. The old secret is retired manually once the receiver confirms it has rotated.

## Replay Protection

`X-Timestamp` skew alone is not sufficient — it bounds *how old* a replayed request can be, not
*whether* it has already been processed once within that window.

- Receivers MUST maintain a nonce cache keyed on the event's `id` (equivalently, `X-Event-Id`).
- Retention: at least the `±5 min` skew window; **24 hours is RECOMMENDED** so that a receiver
  that was down for part of the skew window still catches a redelivery.
- On a duplicate `id` within the retention window, the receiver MUST treat the event as already
  handled and return `200 OK` (or its normal success status) without reapplying side effects — a
  duplicate is not a receiver-side error, so it MUST NOT be surfaced as one to the sender's retry
  logic.

## Subscription Management

- `POST /webhook_subscriptions` — create a subscription. Request: `url`, `events` (array of
  `event_type` patterns, e.g. `["ticket.created", "ticket.updated"]`). Response (`201`): the
  subscription resource **plus a `secret` field containing the signing secret**.
- The `secret` is delivered **exactly once**, in the `201` response body. It is never returned by
  any subsequent `GET` and is not recoverable — only rotatable (create a new secret via the
  rotation endpoint, which again returns it exactly once).
- `GET /webhook_subscriptions` / `GET /webhook_subscriptions/{id}` — list/read subscriptions.
  Never includes `secret`.
- `DELETE /webhook_subscriptions/{id}` — cancel a subscription; `204`.

## Retries, Backoff, and Dead-Lettering

- Non-2xx responses (and connection failures/timeouts) are retried with exponential backoff and
  jitter, for up to **24 hours** from first attempt, matching the idempotency-cache floor in
  [CONSTANTS.md](CONSTANTS.md) so a very-delayed retry cannot land after the receiver has expired
  its own dedupe window.
- After the retry window is exhausted, the event is moved to a dead-letter queue.
- `GET /webhook_subscriptions/{id}/dead_letters` — list dead-lettered events for a subscription
  (cursor-paginated per [QUERYING.md](QUERYING.md)).
- `POST /webhook_subscriptions/{id}/dead_letters/{event_id}:replay` — re-attempt delivery of one
  dead-lettered event on demand.

## References

- RFC 2104, HMAC: Keyed-Hashing for Message Authentication —
  <https://www.rfc-editor.org/rfc/rfc2104>
