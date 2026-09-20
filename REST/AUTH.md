# Authentication & Authorization

This document is the complete specification for [API.md](API.md) §9, which keeps only a quick
reference and delegates here, matching how §5/§18/§19 delegate to their own documents.

## Bearer Tokens

- Clients authenticate with OAuth2/OIDC Bearer tokens: `Authorization: Bearer <token>`.
- Tokens MUST be JWTs (RFC 7519) or introspectable opaque tokens; this document assumes JWTs.
- No secrets in URLs, ever — not in query parameters, not in path segments.
- Token TTLs MUST be short (minutes to low hours for access tokens); refresh tokens rotate on use.

### Token Validation

A server MUST validate every incoming token on every request; it MUST NOT rely on a gateway
having already done so unless that trust boundary is documented and enforced by network policy.

- **Issuer (`iss`)**: MUST match one of the server's configured trusted issuers exactly.
- **Audience (`aud`)**: MUST include an identifier for this API. A token minted for a different
  audience MUST be rejected even if the issuer is trusted — this is the standard confused-deputy
  prevention for Bearer tokens.
- **Expiry (`exp`)**: MUST be checked. A permitted clock skew of **±60 seconds** is allowed when
  comparing `exp`/`nbf` against server time; do not use the ±5 minute webhook skew from
  [CONSTANTS.md](CONSTANTS.md) here, it governs a different mechanism.
- **JWKS caching and key rotation**: Servers SHOULD cache the issuer's JWKS document and MUST
  respect its `Cache-Control` headers, with a floor of 5 minutes and a ceiling of 24 hours to
  bound the blast radius of a compromised key that is still cached.
- **Unknown `kid`**: If the token's `kid` is not present in the cached JWKS, the server MUST
  perform one forced refresh of the JWKS document before rejecting the token. If the `kid` is
  still unknown after that refresh, reject with `401 UNAUTHENTICATED`. Servers MUST rate-limit
  forced refreshes per unknown `kid` to prevent a flood of invalid tokens from becoming a
  JWKS-endpoint denial-of-service.

An expired token returns `401` with `code: "TOKEN_EXPIRED"` (see
[STATUS_CODES.md](STATUS_CODES.md)); any other validation failure (bad signature, wrong issuer,
wrong audience, malformed token) returns `401` with `code: "UNAUTHENTICATED"`.

## Scopes

- **Naming convention**: `<resource>:<action>`, all lowercase, e.g. `tickets:read`,
  `tickets:write`, `tickets:admin`. `<action>` SHOULD be one of `read`, `write`, `admin` unless
  the resource genuinely needs a finer verb (e.g. `tickets:export`).
- **Composition**: an endpoint MAY require more than one scope (all of them, not any of them,
  unless documented otherwise); document the required scope(s) per endpoint per API.md §24. A
  broader scope (`tickets:admin`) MUST NOT be assumed to imply a narrower one (`tickets:write`)
  unless the server explicitly defines that hierarchy — implicit implication is how privilege
  creeps in silently.
- **403 body**: an authenticated caller missing a required scope gets `403` with
  `code: "INSUFFICIENT_PERMISSIONS"` and a `detail` that names the missing scope(s) — this is
  diagnostic information for the token's own owner, not a leak, since they already know they
  have the token.

## Tenant Isolation

- Every request that resolves a resource by identifier MUST also check that the resource belongs
  to the caller's tenant, even when the identifier space is globally unique (e.g. UUIDv7). A
  globally unique identifier is not an authorization check.
- Resource identifiers MUST NOT be usable to probe for the existence of resources in another
  tenant. A caller MUST NOT be able to distinguish "this id belongs to another tenant" from "this
  id does not exist" — see the 403-vs-404 decision below, which exists specifically to close this
  channel.
- Identifiers MUST NOT be sequential or otherwise guessable in a way that lets a caller enumerate
  another tenant's resources; UUIDv7 (D10) satisfies this while still being time-sortable.

## API Keys for Machine Clients

- **Format**: a versioned prefix plus a high-entropy secret, e.g. `sk_live_<32+ random bytes,
  base62>`. The prefix identifies the key type and environment; it MUST NOT leak into logs
  without the secret portion being redacted.
- **Storage**: servers store only a salted hash (e.g. Argon2id or SHA-256 with a per-key salt) of
  the secret, never the plaintext. A leaked database MUST NOT be sufficient to recover usable
  keys.
- **Rotation**: keys MUST be rotatable without downtime — a client can hold two active keys
  during a rotation window, and the old key is revoked once the new one is confirmed in use.
- **Why API keys are weaker than OAuth2 client credentials**: an API key is a single long-lived
  bearer secret with no built-in expiry, no audience binding, and no standardized rotation
  protocol — compromise is permanent until someone notices and revokes it by hand. OAuth2 client
  credentials (RFC 6749 §4.4) issue short-lived access tokens from a longer-lived client secret,
  so a leaked access token self-expires and the blast radius of a leaked client secret is bounded
  by how quickly it's rotated through the token endpoint rather than by manual key revocation.
  API keys SHOULD be limited to machine clients that cannot implement a token exchange flow.

## The `WWW-Authenticate` Challenge

Every `401` response MUST include a `WWW-Authenticate` header in the RFC 6750 §3 challenge form:

```text
WWW-Authenticate: Bearer realm="api.example.com", error="invalid_token", error_description="the access token expired"
```

- `realm` identifies the protection space and SHOULD be the API's hostname.
- `error` is one of RFC 6750's registered values: `invalid_request`, `invalid_token`, or
  `insufficient_scope`. It is a fixed, small vocabulary — it is not the Problem Details `code`
  and MUST NOT be confused with it.
- `error_description` is a short, human-readable diagnostic. It MUST NOT contain anything beyond
  what the Problem Details body already discloses.
- A `403` response (the caller authenticated successfully but lacks permission) MUST NOT include
  `WWW-Authenticate` — the header is specifically for authentication challenges, not authorization
  failures.

## 403 vs 404

Whether a resource the caller may not know exists returns `403` or `404` is an
information-disclosure choice, and every endpoint MUST make it deliberately rather than by
accident of implementation order (e.g. "check existence, then check permission" silently chooses
403-always).

**Default rule:**

- Return **`404 NOT_FOUND`** when the caller has no access to the resource at all — no scope, no
  tenant relationship, nothing that would let them legitimately learn the resource exists. This
  is the default for cross-tenant lookups.
- Return **`403 FORBIDDEN`** when the caller may legitimately know the resource exists (e.g. it
  is within their own tenant, or its existence is otherwise not sensitive) but lacks permission
  to perform this specific action on it.

The endpoint's documentation (API.md §24, Authorization subsection) MUST state which of the two
applies. When in doubt, prefer `404` — it is the safer default because it never confirms
existence to a caller who should not be able to infer it.

## References

- RFC 6749, The OAuth 2.0 Authorization Framework —
  <https://www.rfc-editor.org/rfc/rfc6749>
- RFC 6750, The OAuth 2.0 Authorization Framework: Bearer Token Usage —
  <https://www.rfc-editor.org/rfc/rfc6750>
- RFC 7519, JSON Web Token (JWT) — <https://www.rfc-editor.org/rfc/rfc7519>
- RFC 7517, JSON Web Key (JWK) — <https://www.rfc-editor.org/rfc/rfc7517>
