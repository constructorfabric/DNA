# React Frontend — Usage Patterns

## Types & Client

- Generate TS types from OpenAPI (e.g., `openapi-typescript`)
- Use TanStack Query; compose a thin client with auth, error parsing, and retry
- The client MUST expose response metadata (`ETag`, `Headers`), not just the parsed body —
  optimistic locking, rate-limit headers, `Location`, `Deprecation` and
  `Idempotency-Replayed` are all otherwise unreachable

```ts
import { getAuthToken } from './auth'; // Example auth token provider

// REQUIRED top-level member of every Problem Details body (see STATUS_CODES.md registry).
// Clients localize by `code`; `title`/`detail` are English diagnostics for developers and
// logs and MUST NOT be shown to end users.
export type ProblemDetails = {
  type: string;
  title: string;
  status: number;
  detail?: string;
  code: string;
  instance?: string;
  errors?: Array<{ field: string; code: string; message: string }>;
};

export class ApiError extends Error {
  problem: ProblemDetails;
  status: number;
  headers: Headers;

  constructor(problem: ProblemDetails, status: number, headers: Headers) {
    super(problem.title || 'An API error occurred');
    this.name = 'ApiError';
    this.status = status;
    this.headers = headers;
    this.problem = problem;
  }
}

export type JsonResponse<T> = {
  data: T;
  etag: string | null;
  status: number;
  headers: Headers;
};

// Returns the full response envelope. Use this whenever a caller needs the `ETag` (for
// `If-Match` on the next write) or any other response header.
export async function fetchJsonWithMeta<T>(url: string, init: RequestInit = {}): Promise<JsonResponse<T>> {
  const token = getAuthToken(); // Assume a function that retrieves the bearer token
  const hasBody = init.body !== undefined;
  const res = await fetch(url, {
    ...init,
    headers: {
      // Every 4xx/5xx uses problem+json; accept both so the body always parses.
      'Accept': 'application/json, application/problem+json',
      // Only set Content-Type when there is a body — an unconditional Content-Type turns
      // cross-origin GETs into CORS preflights (see API.md CORS guidance).
      ...(hasBody && { 'Content-Type': 'application/json; charset=utf-8' }),
      ...(token && { 'Authorization': `Bearer ${token}` }),
      ...(init.headers || {}),
    },
    credentials: 'omit',
  });

  if (!res.ok) {
    const problem: ProblemDetails = await res.json().catch(() => ({
      type: 'about:blank',
      title: res.statusText,
      status: res.status,
      code: 'UNKNOWN_ERROR',
    }));
    throw new ApiError(problem, res.status, res.headers);
  }

  // Handle 204 No Content
  if (res.status === 204) {
    return { data: undefined as T, etag: res.headers.get('ETag'), status: res.status, headers: res.headers };
  }

  const data: T = await res.json();
  return { data, etag: res.headers.get('ETag'), status: res.status, headers: res.headers };
}

// Thin wrapper for the common case where only the body is needed.
export async function fetchJson<T>(url: string, init: RequestInit = {}): Promise<T> {
  const { data } = await fetchJsonWithMeta<T>(url, init);
  return data;
}
```

## Retry with Backoff

Retry only the status codes `STATUS_CODES.md` marks retryable, and only when the request is
either safe (`GET`/`HEAD`/`OPTIONS`) or carries a stable `Idempotency-Key` for the same
logical operation. Respect `Retry-After` when the server sends one; otherwise back off
exponentially with jitter.

```ts
const RETRYABLE_STATUS = new Set([408, 429, 500, 502, 503, 504]);

export type RetryOptions = {
  maxAttempts?: number;
  baseDelayMs?: number;
  maxDelayMs?: number;
};

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

// Exponential backoff with full jitter: delay = random(0, min(maxDelayMs, base * 2^attempt)).
function backoffDelay(attempt: number, baseDelayMs: number, maxDelayMs: number): number {
  const cap = Math.min(maxDelayMs, baseDelayMs * 2 ** attempt);
  return Math.random() * cap;
}

export async function withRetry<T>(fn: () => Promise<T>, options: RetryOptions = {}): Promise<T> {
  const { maxAttempts = 4, baseDelayMs = 250, maxDelayMs = 8_000 } = options;

  for (let attempt = 0; ; attempt++) {
    try {
      return await fn();
    } catch (err) {
      const isRetryable = err instanceof ApiError && RETRYABLE_STATUS.has(err.status);
      if (!isRetryable || attempt >= maxAttempts - 1) {
        throw err;
      }
      const retryAfter = (err as ApiError).headers.get('Retry-After');
      const delayMs = retryAfter ? Number(retryAfter) * 1000 : backoffDelay(attempt, baseDelayMs, maxDelayMs);
      await sleep(delayMs);
    }
  }
}
```

## Idempotency-Key

Generate **one key per mutation attempt at a logical operation** — it MUST stay stable
across that operation's own retries, or the server cannot recognize a replay (see D8 /
`API.md` §8). Generate it once inside the mutation function, never per individual `fetch`
call.

```ts
// Key format: 1-255 printable US-ASCII characters; UUIDv7 or ULID RECOMMENDED (not required).
function newIdempotencyKey(): string {
  return crypto.randomUUID();
}
```

## Cursor Pagination (`useInfiniteQuery`)

Clients MUST NOT parse the `cursor` value — treat it as completely opaque (D3). Direction is
baked into the token at mint time, so paging backward is just sending `prev_cursor` back as
the `cursor` query parameter.

```ts
import { useInfiniteQuery } from '@tanstack/react-query';

type Ticket = {
  id: string;
  title: string;
  priority: 'low' | 'medium' | 'high';
  status: 'open' | 'in_progress' | 'resolved' | 'closed';
  created_at: string;
};

type ListResponse<T> = {
  items: T[];
  page_info?: {
    limit: number;
    next_cursor?: string;
    prev_cursor?: string;
  };
};

export function useTicketsInfinite(filters: { status?: string } = {}) {
  return useInfiniteQuery({
    queryKey: ['tickets', 'infinite', filters],
    queryFn: ({ pageParam }) => {
      const qs = new URLSearchParams({ limit: '25' });
      if (filters.status) qs.set('$filter', `status eq '${filters.status}'`);
      if (pageParam) qs.set('cursor', pageParam);
      return fetchJson<ListResponse<Ticket>>(`/v1/tickets?${qs.toString()}`);
    },
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (lastPage) => lastPage.page_info?.next_cursor,
    getPreviousPageParam: (firstPage) => firstPage.page_info?.prev_cursor,
  });
}
```

`hasNextPage` follows from the presence of `next_cursor` on the last fetched page — there is
no `total_count` to compute it from (see `QUERYING.md`).

## Query Example (single resource, ETag threaded through the cache)

Fetch through `fetchJsonWithMeta` so the `ETag` lives in the query cache alongside the data.
Mutations then read it back with `queryClient.getQueryData` instead of re-fetching just to
get a header.

```ts
import { useQuery } from '@tanstack/react-query';

export function useTicket(id: string) {
  return useQuery({
    queryKey: ['tickets', id],
    queryFn: () => fetchJsonWithMeta<Ticket>(`/v1/tickets/${id}`),
    staleTime: 30_000,
  });
}

// In a component:
// const { data: result } = useTicket(id);
// const ticket = result?.data;
```

## Mutation Example: read-modify-write with `If-Match`

The full cycle: read the cached `ETag`, send it as `If-Match`, and on `412 Precondition
Failed` refetch, re-apply the same patch against the new `ETag`, and retry once. A second
`412` is a genuine conflict — surface it to the caller instead of looping.

```ts
import { useMutation, useQueryClient, type QueryClient } from '@tanstack/react-query';

async function updateTicket(
  id: string,
  patch: Partial<Ticket>,
  queryClient: QueryClient,
): Promise<JsonResponse<Ticket>> {
  // One key for the whole logical operation — stable across the retries below (D8).
  const idempotencyKey = newIdempotencyKey();

  const applyPatch = (etag: string) =>
    withRetry(() =>
      fetchJsonWithMeta<Ticket>(`/v1/tickets/${id}`, {
        method: 'PATCH',
        headers: { 'If-Match': etag, 'Idempotency-Key': idempotencyKey },
        body: JSON.stringify(patch),
      }),
    );

  let cached = queryClient.getQueryData<JsonResponse<Ticket>>(['tickets', id]);
  if (!cached) {
    cached = await fetchJsonWithMeta<Ticket>(`/v1/tickets/${id}`);
    queryClient.setQueryData(['tickets', id], cached);
  }

  try {
    return await applyPatch(cached.etag!);
  } catch (err) {
    if (!(err instanceof ApiError) || err.status !== 412) {
      throw err;
    }
    // Precondition failed: someone else updated the ticket first. Refetch, re-apply, retry once.
    const fresh = await fetchJsonWithMeta<Ticket>(`/v1/tickets/${id}`);
    queryClient.setQueryData(['tickets', id], fresh);
    return applyPatch(fresh.etag!); // a second 412 here propagates as a conflict to the caller
  }
}

export function useUpdateTicket(id: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (patch: Partial<Ticket>) => updateTicket(id, patch, queryClient),
    onSuccess: (result) => {
      queryClient.setQueryData(['tickets', id], result);
    },
    onError: (err) => {
      if (err instanceof ApiError && err.status === 412) {
        // Show a conflict message and let the user re-review the (now-refreshed) ticket.
      }
    },
  });
}
```

## Optimistic Update (rollback via `onMutate`/`onError`)

```ts
export function useUpdateTicketOptimistic(id: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (patch: Partial<Ticket>) => updateTicket(id, patch, queryClient),
    onMutate: async (patch) => {
      await queryClient.cancelQueries({ queryKey: ['tickets', id] });
      const previous = queryClient.getQueryData<JsonResponse<Ticket>>(['tickets', id]);
      if (previous) {
        queryClient.setQueryData(['tickets', id], { ...previous, data: { ...previous.data, ...patch } });
      }
      return { previous };
    },
    onError: (_err, _patch, context) => {
      if (context?.previous) {
        queryClient.setQueryData(['tickets', id], context.previous);
      }
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ['tickets', id] });
    },
  });
}
```

## Generated Hooks

Hooks SHOULD be generated from the OpenAPI document (`openapi-typescript` plus a hook
generator, e.g. `orval` or a TanStack Query codegen plugin) rather than hand-written, so
query keys, request shapes and response types stay in sync with the spec automatically. The
hooks in this guide are illustrative of the underlying patterns, not a template to copy as
hand-maintained production code.

## Norms not yet covered by this guide

- `$filter` / `$select` construction helpers (building and validating OData query strings)
- Batch endpoints (`:batch`, `:batchUpdate`, `:batchDelete`)
- Upload flows (multipart / pre-signed URLs)
- Webhook receipt — this is a server-side concern, not a React client one
