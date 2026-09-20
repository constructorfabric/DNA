# Uploads

`README.md` declares "uploads" in scope; this document is what backs that claim. It covers binary
content — the JSON-only rules elsewhere in this corpus do not apply to it.

## Direct Multipart vs Pre-Signed URL

Two upload paths exist; an endpoint MUST document which one it uses and MUST NOT offer both for
the same resource without a stated reason.

- **Multipart direct upload** (`POST` with `multipart/form-data` straight to the API): appropriate
  only for small, server-processed content — a threshold of **10 MB** is RECOMMENDED. The request
  ties up an API handler for the duration of the transfer, so it MUST respect the handler timeout
  in [CONSTANTS.md](CONSTANTS.md).
- **Pre-signed URL** (the API issues a short-lived URL for a direct `PUT`/`POST` to object
  storage): this is the **default for anything user-supplied and large** — any file whose size is
  not bounded by the 10 MB threshold above, or whose size is simply unknown up front. The flow is:
  1. Client requests an upload slot: `POST /uploads` with `filename`, `declared_content_type`,
     and `declared_size_bytes`.
  2. Server returns `201` with an `upload_url` (pre-signed, single-use, short-lived — 15 minutes
     RECOMMENDED) and an `upload_id`.
  3. Client `PUT`s the file bytes directly to `upload_url`.
  4. Client notifies completion: `POST /uploads/{upload_id}:complete`, which triggers the
     validation pipeline below and returns `202` if a scan is pending, `200`/`201` if the upload
     is immediately usable.

## Resumable Uploads

Large or unreliable-network uploads MUST support resuming a partial transfer rather than
restarting it. This corpus does **not** invent a resumable protocol: **`tus`
(<https://tus.io/protocols/resumable-upload>) is RECOMMENDED**. Reasons:

- It already solves chunking, offset negotiation, and checksum verification, all of which a
  bespoke protocol would have to redesign and re-test.
- Client libraries exist for every major platform, so adopting it does not become an
  SDK-maintenance burden the way a custom protocol would.
- It composes cleanly with the pre-signed URL flow above: the pre-signed URL is the `tus` upload
  endpoint on object storage rather than a raw `PUT` target.

An endpoint that expects large files (video, disk images, database exports) SHOULD offer the
`tus` endpoint instead of a single-shot `PUT`.

## Size Limits

The **1 MB `application/json` payload cap** in [CONSTANTS.md](CONSTANTS.md) is a JSON cap; it
does not apply to binary content, which has no single corpus-wide limit. Every upload endpoint
MUST document its own maximum size in bytes. A request declaring or delivering a size over that
endpoint's documented limit is rejected with `413 REQUEST_TOO_LARGE`
(see [STATUS_CODES.md](STATUS_CODES.md)) — checked against `declared_size_bytes` before the
pre-signed URL is issued where possible, and re-checked against the actual transferred size at
`:complete`, since a caller can lie in the declaration.

## Content Sniffing and Allow-Lists

The client-declared `Content-Type` MUST NOT be trusted — it is caller-supplied metadata, not a
verified fact about the bytes.

- The server MUST sniff the actual content type from the file's magic bytes at `:complete` time.
- The server MUST enforce an **allow-list** of accepted types per endpoint (e.g. an avatar upload
  endpoint allow-lists `image/png`, `image/jpeg`, `image/webp`). A deny-list MUST NOT be used —
  a deny-list is a list of what you thought of, an allow-list is a list of what you tested.
- A sniffed type outside the endpoint's allow-list, or a mismatch between the declared and
  sniffed type severe enough to indicate spoofing (e.g. declared `image/png`, sniffed
  `application/x-executable`), is rejected with `415 UNSUPPORTED_MEDIA_TYPE`.
- The stored filename MUST be normalized: strip path separators and control characters, cap
  length, and derive the stored extension from the sniffed type rather than trusting the
  client-supplied filename's extension.

## Virus / Malware Scanning

- Every uploaded file MUST be scanned before it is served back to any consumer other than the
  uploader.
- Scanning is asynchronous: `:complete` returns `202 Accepted` with a `Location` pointing at the
  same async job resource shape as API.md §11 (`status: queued|running|succeeded|failed`), not a
  bespoke shape.
- While a scan is `queued` or `running`, the file is **not retrievable** by any download endpoint;
  a request for it returns `202` with the job's `Location`, mirroring how a client would already
  poll an async job.
- A scan result of `failed` (malware detected) permanently rejects the upload: the object is
  deleted from storage and the job resource records `error` as a Problem Details body with
  `code: "CONTENT_BLOCKED"` — the same code used elsewhere for legally/policy-blocked content
  (see [STATUS_CODES.md](STATUS_CODES.md)).
- A scan result of `succeeded` marks the upload retrievable; only at this point does it become
  eligible for the download-URL flow below.

## Download URLs

- Uploaded content is served through **short-lived pre-signed `GET` URLs**, never a permanent
  public URL. A **15 minute** expiry is RECOMMENDED, matching the upload-slot expiry above; an
  endpoint MAY choose shorter for sensitive content.
- Each request for a download URL MUST re-check the caller's authorization at issuance time —
  a previously-issued download URL does not carry authorization, only time-boxed access to a
  specific object, so authorization changes are respected on the next issuance regardless of
  whether older URLs have expired yet.

## Interaction with `Idempotency-Key`

- `POST /uploads` (slot creation) and `POST /uploads/{upload_id}:complete` are both mutating
  `POST`s and follow [D8](CONSTANTS.md) exactly: clients SHOULD send `Idempotency-Key`, servers
  MUST honour it. A replayed `:complete` call with the same key and same fingerprint returns the
  cached result (including a cached `202` for an in-progress scan) rather than re-triggering the
  scan.
- The raw byte transfer to the pre-signed URL itself is **not** an API request in this corpus's
  sense and carries no `Idempotency-Key` — object storage's own conditional-write semantics
  (e.g. `If-None-Match` on the storage `PUT`) govern that step, if the storage backend supports
  it.

## Interaction with Async Jobs

Upload completion and virus scanning reuse the async job resource from API.md §11 directly rather
than introducing a parallel status model — a client that already knows how to poll `GET
/jobs/{id}` needs to learn nothing new to poll an upload scan. The `result` of a succeeded upload
job is the finished, retrievable resource (or a reference to it); the `error` of a failed one is a
Problem Details body per API.md §7, matching the DNA-E06 correction to the generic job shape.

## Status Codes Used

| Code | When |
|---|---|
| `202 Accepted` | Scan is pending; poll the linked job (also used at `:complete` while the file is being processed). |
| `413 REQUEST_TOO_LARGE` | Declared or actual size exceeds the endpoint's documented limit. |
| `415 UNSUPPORTED_MEDIA_TYPE` | Sniffed content type is outside the endpoint's allow-list, or contradicts the declared type. |
| `422 VALIDATION_ERROR` | The upload slot request itself is well-formed but semantically invalid (e.g. `declared_size_bytes` is zero or negative). |

See [STATUS_CODES.md](STATUS_CODES.md) for the full registry these codes are drawn from.
