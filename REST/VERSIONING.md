# API Versioning & Compatibility

This document defines versioning strategy, compatibility rules, and deprecation practices for REST APIs.

## Table of Contents

- [Versioning Strategy](#versioning-strategy)
- [Compatibility Rules](#compatibility-rules)
- [Breaking vs Non-Breaking Changes](#breaking-vs-non-breaking-changes)
- [Deprecation Process](#deprecation-process)
- [Version Migration](#version-migration)
- [Client Guidelines](#client-guidelines)
- [Implementation Examples](#implementation-examples)

## Versioning Strategy

### Version Format

- **Path-based versioning**: `/v1`, `/v2`, etc.
- **Semantic structure**: Major version only in URL path
- **Internal versioning**: Use semantic versioning (e.g., `1.2.3`) internally for tracking

```
https://api.example.com/v1/users
https://api.example.com/v2/users
```

### Version Lifecycle

1. **Development**: `v1-alpha`, `v1-beta` (internal/staging only)
2. **Stable**: `v1` (production ready)
3. **Deprecated**: `v1` (sunset period)
4. **Retired**: `v1` (no longer available)

## Compatibility Rules

### Backward Compatibility (Within Major Version)

**MUST maintain compatibility** for:
- Existing endpoint URLs
- Request/response field names and types
- HTTP status codes for existing scenarios
- Authentication mechanisms
- Core functionality behavior

**MAY be added** without breaking compatibility:
- New optional fields in requests
- New fields in responses
- New endpoints
- New HTTP methods on existing resources
- Additional enum values (with graceful degradation)
- Additional query parameters

### Forward Compatibility (Client Resilience)

Clients **MUST** be designed to:
- Ignore unknown fields in responses
- Handle additional enum values gracefully
- Not rely on field order in JSON objects
- Treat missing optional fields as absent/default

## Breaking vs Non-Breaking Changes

### ✅ Non-Breaking Changes

**Request Changes**:
- Adding optional fields
- Adding optional query parameters
- Adding new enum values to optional fields
- Making required fields optional
- Relaxing validation rules

**Response Changes**:
- Adding new fields
- Adding new enum values
- Adding new optional headers
- Providing more detailed error messages
- Improving performance/response times

**Endpoint Changes**:
- Adding new endpoints
- Adding new HTTP methods to existing resources
- Adding new optional headers

### ❌ Breaking Changes

**Request Changes**:
- Removing fields
- Making optional fields required
- Changing field types
- Changing field semantics
- Removing enum values
- Tightening validation rules
- Changing URL structure

**Response Changes**:
- Removing fields
- Changing field types
- Changing field semantics
- Removing enum values
- Changing HTTP status codes for existing scenarios
- Changing error response format

**Endpoint Changes**:
- Removing endpoints
- Removing HTTP methods
- Changing authentication requirements
- Changing rate limits significantly

## Deprecation Process

### Deprecation Headers

When deprecating APIs, include these headers:

```http
Deprecation: true
Sunset: Wed, 31 Dec 2025 23:59:59 GMT
Link: <https://docs.api.example.com/migration/v1-to-v2>; rel="deprecation"
```

### Deprecation Timeline

1. **Announcement** (e.g. T-12 months):
   - Publish deprecation notice
   - Update documentation
   - Add deprecation headers

2. **Warning Period** (e.g. T-6 months):
   - Start logging deprecation warnings
   - Notify active API consumers
   - Provide migration guides

3. **Sunset Period** (e.g. T-3 months):
   - Increase warning frequency
   - Consider rate limiting deprecated endpoints
   - Direct support for migration

4. **Retirement** (T-0):
   - Remove deprecated version
   - Return 410 Gone for deprecated endpoints

### Deprecation Response Format

For deprecated endpoints, maintain functionality but add warnings via **HTTP headers** (as specified in main API guidelines):

```http
HTTP/1.1 200 OK
Deprecation: true
Sunset: Wed, 31 Dec 2025 23:59:59 GMT
Link: <https://docs.api.example.com/migration/v1-to-v2>; rel="deprecation"
Content-Type: application/json

{
  /* normal response format - no wrapper for single objects, "items" + "page_info" for lists */
}
```

## Version Migration

### Migration Strategy

**Gradual Migration**:
- Support overlapping versions (typically 2 major versions)
- Provide clear migration paths
- Offer dual-write capabilities for data changes
- Maintain feature parity during transition

**Migration Tools**:
- Automated compatibility checkers
- Code generation for new SDKs
- Migration scripts for common patterns
- Sandbox environments for testing

### Version Negotiation

**Path-based (Recommended)**:
```http
GET /v2/users HTTP/1.1
Host: api.example.com
```

**Header-based (Alternative)**:
```http
GET /users HTTP/1.1
Host: api.example.com
API-Version: 2
```

## Client Guidelines

### Robust Client Design

**Version Handling**:
- Always specify API version explicitly
- Handle version-specific responses gracefully
- Implement fallback mechanisms for deprecated features

**Error Handling**:
```json
{
  "type": "https://api.example.com/errors/version-not-supported",
  "title": "API Version Not Supported",
  "status": 400,
  "detail": "API version 'v3' is not supported. Supported versions: v1, v2",
  "supported_versions": ["v1", "v2"],
  "latest_version": "v2"
}
```

**Future-Proofing**:
- Use strongly-typed models with unknown field handling
- Implement graceful degradation for new enum values
- Version your own client SDKs alongside API versions

### SDK Versioning

**Client SDK Strategy**:
- Major SDK version tracks API major version
- Minor SDK updates for new features within API version
- Patch SDK updates for bug fixes

```
SDK v2.1.0 → API v2
SDK v2.2.0 → API v2 (new features)
SDK v3.0.0 → API v3
```

## Implementation Examples

### OpenAPI Versioning

```yaml
# OpenAPI 3.1 example
openapi: 3.1.0
info:
  title: Example API
  version: 2.1.0
  description: |
    API version 2.1.0

    **Deprecation Notice**: This API version will be sunset on 2025-12-31.
    Please migrate to v3. See [migration guide](https://docs.api.example.com/migration/v2-to-v3).

servers:
  - url: https://api.example.com/v2
    description: Production v2
  - url: https://api.example.com/v1
    description: Production v1 (deprecated)
    x-deprecated: true
    x-sunset: "2025-12-31T23:59:59.000Z"

paths:
  /users:
    get:
      summary: List users
      deprecated: false  # This endpoint is not deprecated in v2
      responses:
        '200':
          description: Success
          headers:
            Deprecation:
              description: Indicates if the API version is deprecated
              schema:
                type: boolean
              example: false
```

Note: the `Sunset` **header** uses the HTTP-date format (RFC 9110), while the `x-sunset` OpenAPI **extension** above uses ISO-8601; both express the same instant.

### Backward Compatibility Testing

```typescript
// Automated compatibility testing
describe('API Compatibility', () => {
  test('v2 should accept all valid v1 requests', async () => {
    const v1Response = await fetch('/v1/users', v1Request);
    const v2Response = await fetch('/v2/users', v1Request);

    // Core functionality should work
    expect(v2Response.status).toBe(v1Response.status);
    expect(v2Response.data.users).toBeDefined();

    // v2 may include additional fields, but core fields should match
    const v1Users = v1Response.data.users;
    const v2Users = v2Response.data.users;

    v1Users.forEach((v1User, index) => {
      const v2User = v2Users[index];
      expect(v2User.id).toBe(v1User.id);
      expect(v2User.name).toBe(v1User.name);
      // v2 may have additional fields - that's OK
    });
  });
});
```

## Best Practices

### Do's

- ✅ Plan major versions carefully - they're expensive
- ✅ Communicate changes early and often
- ✅ Provide comprehensive migration documentation
- ✅ Support at least 2 major versions simultaneously
- ✅ Use feature flags for gradual rollouts
- ✅ Monitor usage of deprecated endpoints
- ✅ Test backward compatibility automatically

### Don'ts

- ❌ Don't break backward compatibility within major versions
- ❌ Don't remove versions without sufficient notice
- ❌ Don't introduce breaking changes as minor updates
- ❌ Don't rely on clients to handle breaking changes gracefully
- ❌ Don't version internal implementation details
- ❌ Don't create versions for every small change

### Version Planning Checklist

Before creating a new major version:

- [ ] Document all breaking changes
- [ ] Provide migration guide with examples
- [ ] Update OpenAPI specifications
- [ ] Generate new client SDKs
- [ ] Plan deprecation timeline for previous version
- [ ] Set up monitoring for version adoption
- [ ] Test migration scripts with real data
- [ ] Communicate timeline to all stakeholders

---

## References

- [Semantic Versioning](https://semver.org/)
- [RFC 8594 - The Sunset HTTP Header Field](https://www.rfc-editor.org/rfc/rfc8594)
- [API Deprecation Guidelines](https://datatracker.ietf.org/doc/draft-ietf-httpapi-deprecation-header/)
