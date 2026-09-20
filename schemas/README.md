# Schemas

Machine-checkable artifacts for this guideline. [API.md §20](../REST/API.md#20-openapi--codegen)
says to keep schemas DRY via shared components and, before this directory existed, gave
consumers nothing to `$ref`. These three files are that thing, plus the ruleset that enforces
the norms a linter can actually check.

## Files

- **`problem.schema.json`** — standalone JSON Schema (draft 2020-12) for the RFC 9457 Problem
  Details body used by every 4xx/5xx response, including the REQUIRED top-level `code` member
  (DECISIONS.md D6, API.md §7). It has its own `$id` and validates independently of OpenAPI, so
  any JSON Schema validator can check a captured error body against it directly.
- **`components.openapi.yaml`** — a shared OpenAPI 3.1 `components` fragment: `PageInfo`,
  `Problem` (which `$ref`s `problem.schema.json` rather than retyping it), `ValidationError`,
  and the five query parameters (`limit`, `cursor`, `$filter`, `$orderby`, `$select`) in the
  `x-odata-*` vendor extension shape [QUERYING.md](../REST/QUERYING.md) requires.
- **`spectral.yaml`** — a [Spectral](https://github.com/stoplightio/spectral) ruleset encoding
  the norms of this guideline that are mechanically checkable: snake_case property names,
  `.SSS` response timestamps, the `items`/`page_info` envelope, `application/problem+json` with
  a required `code` on every 4xx/5xx, required operational response headers, `$filter`/
  `$orderby` allowlists on collection `GET`s, and the ban on `total_count` in `page_info`. Every
  rule is `severity: error` — see [REST/CHECKLIST.md](../REST/CHECKLIST.md), whose
  machine-checked lines correspond to these rule names one-to-one.

## Referencing the components fragment

From your own OpenAPI document, `$ref` the pieces you need instead of retyping them:

```yaml
components:
  schemas:
    PageInfo:
      $ref: 'https://raw.githubusercontent.com/constructorfabric/DNA/main/schemas/components.openapi.yaml#/components/schemas/PageInfo'
  parameters:
    LimitParam:
      $ref: 'https://raw.githubusercontent.com/constructorfabric/DNA/main/schemas/components.openapi.yaml#/components/parameters/LimitParam'
```

If you vendor this repository as a git submodule (README.md "How to Adopt"), reference the local
path instead of the raw URL, e.g. `../docs/DNA/schemas/components.openapi.yaml#/components/...`.
Either way, `$ref` the fragment — do not copy its contents into your document, or you reintroduce
the drift this directory exists to eliminate.

`Problem`'s external `$ref` to `problem.schema.json` works the same way: OpenAPI 3.1 uses the
JSON Schema 2020-12 dialect, so a plain relative or absolute `$ref` to the `.json` file resolves
without any OpenAPI-specific wrapping.

## Running the Spectral ruleset

```bash
npx --yes @stoplight/spectral-cli lint openapi.json \
  --ruleset schemas/spectral.yaml \
  --fail-severity warn
```

`--fail-severity warn` is deliberate: since every rule here is already `severity: error`, this
flag only guards against a future rule being added at a lower severity by mistake.
