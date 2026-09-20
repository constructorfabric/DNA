# Public Library Interface Design (PLID) Requirements

## Overview

A general-purpose, language-agnostic, actionable, LLM-friendly playbook for automated library interface review and for designing stable, ergonomic public library interfaces (SDKs, packages, and modules).

This guide treats public interfaces as long-term contracts, not temporary implementation details.

When building an internal application, you can refactor quickly because you control all callers. When publishing a library, every exported symbol may be copied into dozens of downstream codebases. Decisions become expensive to reverse. This document provides a practical checklist that can be applied to any programming language or framework, and it can serve as a skeleton for language-specific or framework-specific guides.

## Core Principles

A short list of guiding ideas the rest of this document elaborates. Every requirement below traces back to one or more of these.

- **APIs should be easy to use and hard to misuse.** *(Joshua Bloch)*
- **Public surface is a long-term contract.** Be intentional about what is exported; when in doubt, leave it out *(Joshua Bloch)*.
- **Encode meaning in types, not comments.** A well-typed interface fails at compile time; a well-commented one fails in production.
- **Safe by default.** Defaults should be operationally sane; dangerous actions must be explicit.
- **Errors are first-class interface surface.** Make them actionable and structured, not opaque.
- **Documentation and examples are part of the contract.** Consumers copy examples verbatim and read item-level docs more often than they read source; treat both with the same discipline as code.
- **Conform to the ecosystem.** Familiar conventions beat clever novelty.

## Severity Levels

Every requirement below is tagged `CRIT`, `MAJOR`, or `MINOR`. These tags are not decoration — they are the grading scale a review verdict is computed from.

- **CRIT** — a violation blocks approval. The interface MUST NOT ship until it is resolved or an explicit, recorded exception is granted.
- **MAJOR** — a violation MUST be resolved before the next release that exposes the interface publicly; it may be recorded as a tracked follow-up rather than blocking the review.
- **MINOR** — a violation is recorded as advisory and does not block.

A review verdict is the highest unresolved severity found. "No CRIT open" is the approval gate: a review with only MAJOR or MINOR findings open MAY be approved with tracked follow-ups, but a review with any open CRIT finding MUST NOT be approved. See the [Minimal Review/Approval Checklist](#minimal-reviewapproval-checklist) at the end of this document for the concrete set of checks a review applies before reaching that verdict.

## Table of Contents

- [Severity Levels](#severity-levels)

- **Part I — Contract Foundations**
  - [PLID-10 Public Contract Definition & Stability](#plid-10-public-contract-definition--stability)
  - [PLID-11 Meaningful Types & Misuse-Resistant Modeling](#plid-11-meaningful-types--misuse-resistant-modeling)
  - [PLID-12 Consistency Across Surface Area](#plid-12-consistency-across-surface-area)

- **Part II — Evolution & Governance**
  - [PLID-20 Evolvability & Future Change](#plid-20-evolvability--future-change)
  - [PLID-21 Governance, Versioning & Release Discipline](#plid-21-governance-versioning--release-discipline)

- **Part III — Boundaries & Ecosystem Integration**
  - [PLID-30 Dependency & Boundary Design](#plid-30-dependency--boundary-design)
  - [PLID-31 Cross-Language & Wire Contracts](#plid-31-cross-language--wire-contracts)

- **Part IV — Usability & Consumer Experience**
  - [PLID-40 Ergonomics & Discoverability](#plid-40-ergonomics--discoverability)
  - [PLID-41 Validation, Safe Defaults & Construction](#plid-41-validation-safe-defaults--construction)
  - [PLID-42 Documentation as Product](#plid-42-documentation-as-product)
  - [PLID-43 Testing & Verification of Public Contracts](#plid-43-testing--verification-of-public-contracts)

- **Part V — Runtime Behavior & Operations**
  - [PLID-50 Error & Failure Contracts](#plid-50-error--failure-contracts)
  - [PLID-51 Concurrency, Cancellation & Execution Model](#plid-51-concurrency-cancellation--execution-model)
  - [PLID-52 Performance & Resource Contracts](#plid-52-performance--resource-contracts)
  - [PLID-53 Observability & Operational Readiness](#plid-53-observability--operational-readiness)
  - [PLID-54 Security Boundaries & Hazardous Operations](#plid-54-security-boundaries--hazardous-operations)
  - [PLID-55 State Mutation & Side Effects](#plid-55-state-mutation--side-effects)
  - [PLID-56 Data Lifecycle & Retention](#plid-56-data-lifecycle--retention)

- [Minimal Review/Approval Checklist](#minimal-reviewapproval-checklist)
- [References](#references)


# PLID-10 Public Contract Definition & Stability

A public interface must explicitly define what consumers are allowed to rely on.

Anything a consumer can import, call, configure, match on, serialize, automate against, or copy from documentation can become part of the long-term contract.

## PLID-10.01 Public Surface Inventory (CRIT)

Accidentally public items often become permanent support obligations. Maintain a clear inventory of every supported public-facing surface.

This includes:

- exported functions, methods, constructors, and types
- interfaces, traits, protocols, callbacks, and extension points
- configuration schemas, environment variables, and feature flags
- error types, error codes, and status values
- serialized payloads, schema fields, event shapes, and wire names
- documented behavior, examples, and migration guides

Libraries should read environment variables only when following a well-known ecosystem convention (proxy settings, OpenTelemetry endpoints, log filters); arbitrary env-driven configuration belongs to the application layer, not the library.

If the library ships a companion CLI or daemon, treat its surface (flags, exit codes, signal handling) as a separate contract with its own stability declarations.

## PLID-10.02 Stability Declaration (CRIT)

Consumers need to understand adoption risk before depending on a feature. Every public feature must declare its stability tier.

Tiers:

- **stable** — production-ready; backward compatibility guaranteed until the next major version.
- **preview** — feature is stabilizing; breaking changes possible but unlikely before promotion to stable.
- **experimental** — no compatibility promise; may be reshaped or removed at any minor release.
- **deprecated** — discouraged; scheduled for removal in the next major version; migration path documented.
- **retired** — no longer served; requests receive `410 Gone`.

[`../REST/VERSIONING.md`](../REST/VERSIONING.md) applies these tiers to API versions.

## PLID-10.03 Compatibility Dimensions (CRIT)

A release may preserve source compatibility while still breaking serialized payloads, runtime expectations, or behavior. State compatibility separately for each relevant dimension.

Common dimensions include:

- source compatibility
- binary or ABI compatibility
- wire compatibility
- runtime or toolchain compatibility
- behavioral compatibility
- operational compatibility

## PLID-10.04 Public Dependency Awareness (MAJOR)

Your stability is constrained by every external contract you leak into your own interface. If the public interface exposes third-party types or protocols, document that coupling explicitly.

## PLID-10.05 Contract Examples as Contract Surface (MAJOR)

Consumers often copy examples verbatim and then rely on that usage pattern for years. Treat official examples and quick starts as public contract, not marketing material.

## PLID-10.06 Minimize Public Surface (MAJOR)

Every exported symbol is a long-term support obligation. Adding a public item is a one-line change; removing it requires a major version bump, a migration guide, and downstream churn. This asymmetry is the dominant cost driver in library evolution.

Default to keeping types, functions, and modules private until there is a concrete consumer need to expose them. When unsure whether something should be public — leave it out *(Joshua Bloch)*. You can always add it later; you can rarely take it back.


# PLID-11 Meaningful Types & Misuse-Resistant Modeling

Primitive values are cheap for authors and expensive for consumers. Good interfaces encode meaning in types, names, and shapes so the intended use is obvious and the wrong use is harder to express.

## PLID-11.01 Replace Ambiguous Primitives (CRIT)

Ambiguous primitives create swapped arguments, invalid inputs, unclear call sites, and brittle downstream logic. Do not expose raw strings, integers, or booleans where a domain type, enum, validated wrapper, or small structured type would communicate meaning more safely.

## PLID-11.02 Domain Identifier Safety (CRIT)

Domain-typed identifiers prevent wrong-resource bugs and cross-tenant or cross-entity mistakes. Identifiers from different domains must not be interchangeable.

Examples:

- `UserId`
- `OrderId`
- `TenantId`
- `ProjectId`

## PLID-11.03 Make Invalid States Hard or Impossible to Express (CRIT)

Consumers should not need to reverse-engineer which combinations are forbidden. If a value combination can represent nonsense, redesign the model so invalid states are unrepresentable or rejected early.

## PLID-11.04 Units, Precision & Numeric Semantics (MAJOR)

Unit and precision bugs are common, expensive, and hard to notice in review. If a number represents time, size, rate, money, quantity, distance, or precision-sensitive data, the unit and interpretation must be explicit.

Use, in order of preference:

- built-in or stdlib types where they exist (e.g., `time.Duration`/`time.Time` in Go, `std::time::Duration` in Rust — see [`../languages/RUST.md`](../languages/RUST.md) for the DNA-mandated date-time crate, `TimeSpan`/`DateTime`/`decimal` in .NET, `decimal.Decimal` in Python) — do not invent parallel types when the ecosystem already has a canonical one
- domain-specific wrapper types when no canonical stdlib type fits (e.g., `Money`, `Bytes`, `RequestsPerSecond`)
- unit-bearing names (e.g., `timeoutMs`, `sizeBytes`) as a fallback when a wrapper type is impractical
- explicit overflow, precision, and rounding rules documented at the boundary

## PLID-11.05 Replace Boolean Flags with Modes (MAJOR)

Boolean flags are unclear at the call site and usually fail to scale once a third state appears. Avoid boolean parameters or fields when the value represents a mode, strategy, or policy.

## PLID-11.06 Lifecycle & Phase Modeling (MAJOR)

Call-order bugs are subtle, high-cost, and often avoidable through better modeling. If call order matters, encode lifecycle or phase in the interface design.

Examples include:

- uninitialized versus ready
- disconnected versus connected
- unauthenticated versus authenticated
- draft versus committed


# PLID-12 Consistency Across Surface Area

Large libraries fail not because each API is bad, but because each API is different.

## PLID-12.01 Internal Consistency (CRIT)

If similar operations differ in naming, parameter order, return shapes, async model, or error semantics, consumers pay permanent cognitive tax.

Ensure equivalent operations follow shared patterns.

Examples:

- `getUser(id)` vs `fetchOrder(id)` vs `loadProject(id)` → unify verb model
- `(ctx, id)` everywhere or nowhere
- all paginated endpoints use same cursor model

## PLID-12.02 Principle of Least Surprise (CRIT)

Public APIs should behave how experienced users expect in that ecosystem unless there is a strong reason not to.

## PLID-12.03 Single Purpose / Cohesion (MAJOR)

An API should do one thing, and do it well *(Joshua Bloch)*. A library whose purpose can be stated in a single sentence is easier to learn, easier to evolve, and easier to replace. When a module accumulates unrelated capabilities, every consumer pays for the parts they do not use, and every refactor risks breaking an unrelated client.

If you cannot describe what the interface is for in one sentence — split it. Two narrow, cohesive libraries beat one broad, vague one.


# PLID-20 Evolvability & Future Change

Good interfaces survive future requirements without forcing unnecessary rewrites.

## PLID-20.01 Additive Growth Paths (CRIT)

If every enhancement requires a breaking change, the design is brittle. Design interfaces so common future additions can be introduced without breaking consumers.

Plan for growth in:

- fields
- optional parameters
- metadata
- variants or cases
- capabilities
- telemetry and tracing context

## PLID-20.02 Closed vs Open Taxonomies (CRIT)

Consumers need to know whether exhaustive matching is safe, risky, or explicitly unsupported. Classify each enum-like set intentionally as either closed or open.

- A **closed taxonomy** is finite by semantics and safe for exhaustive handling.
- An **open taxonomy** is expected to grow and must be designed for forward compatibility.

## PLID-20.03 Decision Ownership (CRIT)

Avoid silent wrong behavior hidden behind catch-all logic. When a new case is introduced, compile-time or migration pain should land where the semantic decision belongs.

- If maintainers own the decision, maintainer code should break first.
- If consumers must choose behavior, consumer migration may be appropriate.

## PLID-20.04 Construction for Future Growth (MAJOR)

Rigid construction patterns make harmless additive change look breaking. Prefer constructors, factories, builders, named options, or configuration objects over direct positional construction when future growth is likely.

## PLID-20.05 Extension Point Discipline (MAJOR)

Extension points constrain future refactoring more than ordinary public methods do. Only add extension points that you can support long-term.

Examples include:

- callbacks
- subclassing or inheritance hooks
- interface or protocol implementations
- plugin mechanisms
- user-defined schema fragments

## PLID-20.06 Keep Implementation Freedom (MAJOR)

Public APIs should expose what consumers must rely on — and no more. Over-specifying behavior in types, signatures, or documentation locks the implementation: tomorrow's optimization, cache layer, retry strategy, or replacement backend becomes a breaking change. *"Keep APIs free of implementation details. They confuse users and inhibit the flexibility to evolve."* — Joshua Bloch.

Document the guarantees consumers can build on (see [PLID-42.03](#plid-4203-behavioral-documentation-crit)), and explicitly mark behaviors that are *not* part of the contract (ordering of debug fields, internal cache TTLs, exact retry counts, log message wording). When in doubt, under-specify rather than over-specify.


# PLID-21 Governance, Versioning & Release Discipline

Good public interfaces require process, not just good intentions.

## PLID-21.01 New Public API Gate (CRIT)

Every public symbol is much cheaper to publish than to support. Before publishing new public surface, ask:

- Is it truly needed?
- Can we support it for years?
- Is the naming mature?
- Is the behavior documented?
- Are tests ready?
- Is the migration and compatibility story understood?

## PLID-21.02 Breaking Change Gate (CRIT)

Many breaking changes are avoidable with slightly better design or staging. Before shipping a breaking change, ask:

- Is additive change still possible?
- Is the consumer impact understood?
- Is migration documented?
- Is the versioning policy being respected?
- Are compatibility notes explicit?

## PLID-21.03 Deprecation Workflow (MAJOR)

Deprecation is part of interface design, not just release bookkeeping. Use staged retirement:

- mark deprecated
- provide a replacement or migration path
- communicate timeline
- remove only in the appropriate breaking release window

## PLID-21.04 Versioning Policy & Toolchain Support (MAJOR)

Consumers need a trustworthy upgrade model, not guesswork. State versioning expectations, supported toolchains or runtimes, and any special compatibility commitments.

## PLID-21.05 Changelog & Release Notes (MAJOR)

Consumers decide whether and how to upgrade based on what the release notes say. Silent or sparse release notes force consumers into defensive reading of diffs.

For each release, record:

- added, changed, deprecated, removed, and fixed public surface
- behavioral changes even when signatures are unchanged
- security-relevant fixes called out explicitly
- migration guidance for any non-trivial change
- minimum supported toolchain/runtime bumps


# PLID-30 Dependency & Boundary Design

Public boundaries should not leak accidental implementation choices.

## PLID-30.01 Third-Party Leakage Review (CRIT)

Review every public dependency type, protocol, or framework symbol that appears in the interface. If the interface exposes dependency-specific types, consumers inherit dependency churn and versioning risk.

## PLID-30.02 Neutral Boundary Types (MAJOR)

Neutral types preserve your ability to refactor internals without breaking consumers. Prefer domain types or broadly stable industry-standard types at the public boundary.

## PLID-30.03 Capability-Scoped Interfaces (MAJOR)

Expose narrow handles or interfaces when different consumer roles need different powers. Smaller surfaces improve safety, comprehension, and long-term evolution.

## PLID-30.04 Do Not Leak Internal Type Parameters & Constraints (MAJOR)

Generic or type parameters, interface constraints, and implementation-detail type requirements in public signatures become part of the contract. Once published, tightening them is a breaking change and loosening them may force cascading changes on consumers.

Prefer:

- hiding internal type parameters behind concrete or opaque public types
- keeping interface constraints on public items minimal and semantically justified
- using abstraction, opaque wrappers, or sealed types when an internal type should not become part of the public surface
- keeping fields private and exposing them through methods, so representation changes do not break consumers

Note: prefer small, composable contracts over large inheritance-style hierarchies where the language ecosystem favors composition. Composition is easier to reason about and usually evolves more safely.

# PLID-31 Cross-Language & Wire Contracts

If multiple languages, runtimes, processes, or generators consume the interface, portability becomes part of the contract.

For HTTP APIs, the concrete DNA contract is [`../REST/API.md`](../REST/API.md) §4 (JSON Conventions).

## PLID-31.01 Stable Serialization Rules (CRIT)

Field names, enum values, defaults, nullability, and missing-field semantics must be intentional and stable. Wire contracts usually outlive in-process APIs and are much harder to migrate.

## PLID-31.02 Language-Neutral Time & Number Semantics (CRIT)

Time and numeric ambiguity becomes much worse once values cross languages and systems. Specify:

- units
- timezone or offset handling
- precision
- rounding behavior
- overflow behavior

## PLID-31.03 Stable String Values for Enums & Codes (MAJOR)

Numeric meaning is fragile across reordering, generation, and mixed-language stacks. Prefer stable string representations over numeric discriminants for wire-visible enum-like values.

## PLID-31.04 Generator-Friendly Schemas (MAJOR)

Design schemas and field names so generated clients can consume them cleanly. Generated clients amplify every awkward naming or schema choice.

Avoid:

- reserved keyword collisions
- ambiguous nullability
- inconsistent casing
- overloaded fields with multiple meanings


# PLID-40 Ergonomics & Discoverability

Consumers should be able to succeed quickly and read code confidently later.

## PLID-40.01 Happy Path Simplicity (CRIT)

If first use is painful, consumers either abandon the interface or misuse advanced features just to get started. The common task must be straightforward, obvious, and minimally ceremonial.

## PLID-40.02 Naming Quality (CRIT)

Use names that are:

- obvious
- consistent
- searchable
- aligned with language and ecosystem norms
- precise about intent

Naming is the first documentation most consumers see. Avoid vague names such as `Manager`, `Helper`, `Util`, or `Thing` unless they are genuinely standard and descriptive in context.

## PLID-40.03 Advanced Path Separation (MAJOR)

Interfaces become hostile when basic workflows require expert-level setup. Advanced capabilities should not burden simple consumers.

Use optional builders, expert configuration, plugin points, or separate advanced entry points instead of forcing every consumer through the most complex shape.

## PLID-40.04 Reader-Time Optimization (MAJOR)

Library authors write the API once; consumers read it repeatedly for years. Optimize for people reading call sites months later, especially during maintenance and incident response.

## PLID-40.05 Ecosystem Convention Alignment (MAJOR)

Predictable interfaces are easier to learn, search, and debug. Prefer familiar conventions over novelty unless a new shape clearly improves safety or correctness.

Consult and follow language-specific API guidelines where they exist — for example, the Rust API Guidelines, the .NET Framework Design Guidelines, and Python's PEP 387 (Backwards Compatibility Policy). See *References* below.

## PLID-40.06 Eliminate Caller-Side Boilerplate (MAJOR)

If every consumer writes the same wrapping, conversion, retry, or cleanup boilerplate around your API, that boilerplate is a design failure of the library — not a fact of life for the user. *"A class should do one thing well and the user should not need to do anything the class could do for them."* — Joshua Bloch.

Treat repetitive consumer code seen in examples, tests, or downstream repos as a signal to reshape the interface.


# PLID-41 Validation, Safe Defaults & Construction

Configuration and object construction are part of the public contract. This section collects the boundary-shaping rules that most directly determine whether the library is correct-by-default.

## PLID-41.01 Typed Configuration (CRIT)

Configuration errors should fail at load time or initialization time, not during live traffic. Prefer typed configuration objects or validated configuration schemas over arbitrary maps or free-form dictionaries.

## PLID-41.02 Boundary Validation on Entry (CRIT)

A fast, precise failure near the boundary — a "fail-fast" boundary — is better than a confusing failure deep inside the system. Validate public inputs as early as possible.

## PLID-41.03 Safe Defaults (MAJOR)

Correct-by-default behavior reduces incident risk and lowers adoption cost. Defaults should be operationally sane and safe.

Examples:

- timeouts enabled
- retries bounded
- secure transport preferred
- logging and telemetry not excessively noisy
- dangerous actions not enabled implicitly

## PLID-41.04 Construction Patterns for Clarity & Growth (MAJOR)

Positional construction is brittle, hard to read, and hard to evolve. Avoid large positional constructors for public interfaces with many options or evolving requirements.

Prefer:

- builders
- named parameters where the language supports them
- options objects
- focused constructors for distinct use cases

## PLID-41.05 Caller-Controlled Ownership & Allocation (MAJOR)

Over-restrictive input types force unnecessary clones, allocations, and intermediate buffers on the caller. Accept the most permissive input the operation actually needs, and let the caller decide whether to pass an owned value, a shared reference, or a read-only view.

Examples:

- accept a read-only view of a string or buffer instead of requiring an owned copy when no ownership transfer is needed
- accept a generic sequence or stream rather than a specific collection type
- return owned values only when ownership is genuinely produced; otherwise allow zero-copy or shared access
- avoid hidden global allocators, thread pools, or singletons when the caller might reasonably want to supply their own

## PLID-41.06 Single Configuration with Sane Defaults (MINOR)

Prefer one configuration model with reasonable defaults over splitting configuration into multiple tiers (e.g., "common" vs "expert"). Two configuration surfaces are hard to maintain, the boundary between them is subjective, and "advanced" sections tend to accumulate everything the team did not want to highlight.

Use per-field markers (e.g., `@advanced`, `@unstable`, doc comments) to flag knobs that should be touched only deliberately, while keeping all configuration in one place.


# PLID-42 Documentation as Product

Documentation is part of the interface, not an optional afterthought.

## PLID-42.01 Entry-Point & Overview Documentation (CRIT)

Consumers need a single place to understand what the library is, what it is not, and how the pieces fit together. Without it, adoption starts from searching scattered symbols.

The top-level entry documentation should include:

- a single canonical landing page — typically a `README.md` for the repo/registry, plus language-native root documentation (`lib.rs` doc comments in Rust, `doc.go` in Go, module-level docstrings in Python)
- a one-paragraph statement of purpose and scope
- the canonical quick-start example
- a map of primary types and their relationships
- pointers to configuration, errors, feature flags, and stability tiers
- link to changelog, migration guides, and supported platforms

## PLID-42.02 Item-Level Documentation (CRIT)

Consumers read API documentation in IDEs and generated reference sites more often than they read repository prose. Every public item should explain:

- what it does
- when to use it
- inputs and outputs
- constraints and invariants
- failure behavior
- lifecycle or ordering caveats

## PLID-42.03 Behavioral Documentation (CRIT)

Document behavioral guarantees that consumers may rely on. Undocumented behavior still becomes relied on; the difference is that maintainers lose control of the contract. Describe:

- ordering
- mutability
- concurrency behavior
- ownership expectations
- performance-sensitive behavior
- compatibility and stability tier

## PLID-42.04 Runnable & Verified Examples (MAJOR)

Examples must serve two audiences at once: a consumer who copies the first working snippet and a maintainer who must keep the contract and the documentation from drifting apart. Therefore examples should both be **runnable** by the user out of the box and **verified automatically in CI** as part of the public contract.

Where the ecosystem provides a built-in mechanism, use it: Rust doctests, Go testable examples, Python doctest or Sphinx doctest, .NET `<example>` blocks paired with xUnit tests. When the language has no such mechanism, place examples in dedicated source files that the test suite builds and runs. Broken examples are usually the first sign that the public contract and documentation have diverged.

Provide examples for:

- quick start
- common workflow
- error handling
- advanced or streaming workflow where relevant

## PLID-42.05 Related-Item Navigation (MAJOR)

Good navigation reduces misuse and shortens learning time. Cross-link adjacent types, helpers, configuration objects, and migration paths.

## PLID-42.06 Documentation Templates & Consistency (MINOR)

Consistency makes large public surfaces easier to skim. Use consistent documentation structure for summaries, invariants, errors, examples, and related items.


# PLID-43 Testing & Verification of Public Contracts

Test promises, not only internals.

## PLID-43.01 Contract Tests (CRIT)

An undocumented implementation detail can change safely; a published guarantee cannot. Test documented guarantees such as validation, ordering, idempotency, error mapping, and lifecycle rules.

## PLID-43.02 Compatibility Verification (CRIT)

Compatibility promises are only real if they are exercised continuously. Verify compatibility claims with fixtures, upgrade tests, old payload tests, or consumer-style integration checks.

## PLID-43.03 Consumer Test Support (MAJOR)

Provide builders, fakes, fixtures, or test-support packages for common downstream testing needs when the ecosystem supports it. Without shared test support, every consumer reimplements similar scaffolding and drifts.


# PLID-50 Error & Failure Contracts

Errors are first-class interface surface and must be designed deliberately.

For HTTP APIs, the concrete DNA contract is [`../REST/STATUS_CODES.md`](../REST/STATUS_CODES.md) as the error-code registry and [`../REST/API.md`](../REST/API.md) §7 as the wire format.

## PLID-50.01 Actionable Error Taxonomy (CRIT)

One opaque failure type forces consumers to guess and often handle errors incorrectly. Consumers must be able to distinguish failures that require different handling.

Typical distinctions include:

- retry later
- fix input
- authenticate again
- permission denied
- not found
- rate limited
- timed out
- internal fault

## PLID-50.02 Cause Preservation (CRIT)

Production debugging depends on root cause chains, machine-readable metadata, and precise context. Do not flatten upstream failures into plain strings when structured cause information can be preserved.

## PLID-50.03 Document Unchecked & Out-of-Band Failures (CRIT)

Failures that bypass the normal error channel (process aborts, uncaught exceptions, assertion failures, fatal runtime errors) are still part of the observable contract even when they are not in the return type. Consumers cannot defend against what they cannot see.

For any public item that may fail without going through the normal error channel, document:

- the conditions that trigger it
- whether it indicates caller misuse or environmental failure
- whether the process or object state is recoverable after the failure
- any safer alternative that returns a structured error instead

## PLID-50.04 Structured Error Data (MAJOR)

Consumers should not parse human text to recover behavior. Place failure-specific actionable metadata in fields, properties, or machine-readable members rather than only in display text.

Examples:

- retry delay
- offending field
- status code
- remote error code
- correlation ID

## PLID-50.05 Failure Semantics (MAJOR)

Two failures with the same message may demand opposite recovery actions. Document relevant failure behavior such as:

- retryability
- idempotency expectations
- timeout meaning
- partial success behavior
- cancellation behavior
- whether the failure is caller-caused, environment-caused, or library-caused

## PLID-50.06 Stable Machine-Oriented Codes (MINOR)

Human display text is not a safe compatibility boundary. For cross-process or cross-language usage, provide stable error codes distinct from human-readable messages.


# PLID-51 Concurrency, Cancellation & Execution Model

Consumers need to understand behavior under parallelism, time, and re-entrancy.

## PLID-51.01 Cancellation & Deadlines (CRIT)

Long-running operations should support cancellation and deadline propagation where the environment allows it. Without cancellation, abandoned work wastes compute, money, and time.

## PLID-51.02 Concurrency Safety Contract (CRIT)

Silence about concurrency guarantees causes races, accidental serialization, or unsafe sharing. Document whether instances, handles, clients, or callbacks are safe for concurrent use.

## PLID-51.03 Blocking, I/O & Background Work Disclosure (MAJOR)

Execution model surprises can cause deadlocks, latency spikes, and scheduler misuse. State whether operations:

- block a thread
- perform network or disk I/O
- start background work
- consume substantial CPU
- may re-enter callbacks or user code

## PLID-51.04 Re-entrancy & Overlap Rules (MAJOR)

Re-entrancy bugs are difficult to diagnose and often only appear in production timing conditions. If callbacks can invoke the library again, or if overlapping calls on the same object are allowed, document that contract explicitly.

## PLID-51.05 Calling-Context Safety (MAJOR)

Public methods rarely execute in isolation; they run inside ambient contexts that constrain what is safe to do, such as open transactions or units of work, held locks or critical sections, event-loop or UI callbacks, signal handlers, and request or session scopes. Calling the wrong operation inside such a context causes lock contention, bloated or long-open transactions, deadlocks, and latency spikes that are only visible under production load.

For each public operation, document and where possible enforce:

- whether it is safe to call while a transaction (or similar unit-of-work) is already open
- whether it performs I/O, network calls, or blocking waits that would extend the holding context
- whether it acquires additional locks, nested transactions, or global resources internally
- recommended placement relative to the ambient context (before opening, inside, or after committing)
- preferred alternatives for long-running variants, such as asynchronous, batched, or post-commit forms

Make unsafe combinations visible at the call site through explicit naming, annotations, or type-level markers (for example, a context-scoped handle whose type differs from the unrestricted one) rather than leaving the constraint to be discovered during an incident.

## PLID-51.06 Serialization versus Parallelism Choices (MINOR)

Consumers need to know whether contention is a design decision or an accidental bottleneck. If the interface intentionally serializes work, state that and explain why.


# PLID-52 Performance & Resource Contracts

Performance-relevant behavior is part of correctness for many consumers.

## PLID-52.01 Streaming versus Buffering (CRIT)

Buffered-only interfaces hide latency, inflate memory use, and prevent timely cancellation. If outputs may be large or incremental, provide a streaming, iterative, or paginated shape rather than forcing full buffering.

## PLID-52.02 Allocation, Copy & Ownership Cost (CRIT)

Cheap-looking APIs can have unexpectedly high cost. Consumers should know whether operations:

- deep copy
- shallow copy
- allocate per call
- reuse buffers
- return shared or view-like data instead of owned copies

## PLID-52.03 Cleanup & Release Semantics (CRIT)

Resource cleanup is part of the public contract. Unclear release behavior leaks sockets, files, handles, locks, and memory, and hides errors that matter for correctness.

Specify and implement:

- whether cleanup is automatic (scope-bound, finalizer, or similar) or requires an explicit `close`, `dispose`, or `shutdown` call
- idempotency of cleanup (calling twice must be safe)
- whether cleanup may block, perform I/O, or fail
- how cleanup errors are surfaced (automatic cleanup paths should generally not raise; provide an explicit fallible close for failures that matter)
- behavior if the object is used after cleanup

## PLID-52.04 Complexity Expectations (MAJOR)

Hidden complexity creates accidental slow systems. Document relevant algorithmic or scaling properties when consumers could reasonably depend on them.

Examples:

- constant-time lookup
- linear scan
- sorting cost
- memory growth with input or time in flight

## PLID-52.05 Ordering, Laziness & Start-of-Work Semantics (MAJOR)

Document whether processing is eager or lazy, preserves input order, or begins work before consumption. These properties affect correctness, cost, and observability.

## PLID-52.06 Pagination Contracts (MAJOR)

Paginated interfaces need stable wire-level semantics, not just page size parameters. Without an explicit pagination contract, consumers cannot safely resume traversal, deduplicate results, or reason about missing and repeated items under concurrent writes.

Document at minimum:

- the pagination model, including whether the interface uses cursor-based, offset-based, keyset, or page-number pagination
- the stability guarantees of that model and when one approach is preferred or unsafe
- snapshot consistency expectations across pages, including whether later pages observe a fixed snapshot or a moving dataset
- duplicate handling expectations, including whether clients must tolerate repeated items across page boundaries
- deleted-row behavior, including whether removals can cause skips, short pages, invalid cursors, or reflow of later results
- sort guarantees, including the exact ordering fields, tie-break rules, and whether the order is total and stable across requests

For HTTP APIs, the concrete DNA contract is [`../REST/QUERYING.md`](../REST/QUERYING.md).


# PLID-53 Observability & Operational Readiness

Production debugging should be designed into the interface from the beginning.

## PLID-53.01 Correlation Context (CRIT)

Support propagation of request, trace, span, or operation identifiers where the platform supports them. Without correlation context, incident analysis becomes expensive log archaeology.

## PLID-53.02 Sensitive Data Safety (CRIT)

Logs, traces, errors, and debug output must avoid leaking secrets or regulated data by default. Observability that leaks secrets creates a security incident while trying to help diagnose one.

Examples include:

- tokens
- passwords
- API keys
- personal data
- session identifiers

## PLID-53.03 Telemetry Hooks (MAJOR)

Consumers need observability that fits the rest of their stack. Integrate with platform-standard logging, metrics, and tracing systems rather than inventing custom observability ecosystems.

## PLID-53.04 Operational Metadata (MAJOR)

Operational metadata improves supportability and automated recovery. Where appropriate, expose typed operational metadata such as request IDs, tenant IDs, rate-limit hints, and retry advice.

## PLID-53.05 Incident-Friendly Naming (MINOR)

Choose field and event names that are easy to grep, search, and recognize quickly during outages. Operational clarity matters most when systems are under stress.

## PLID-53.06 Useful Debug & Display Representations (MINOR)

Default debug and string representations are read far more often than the authors expect: in logs, crash dumps, test failures, REPL sessions, and incident tickets. Empty or uninformative output wastes diagnostic time.

For public types, ensure:

- debug representation is non-empty and identifies the type meaningfully
- display representation, when provided, is stable and user-facing
- secrets and regulated data are redacted in both (see [PLID-53.02](#plid-5302-sensitive-data-safety-crit))
- representations do not accidentally become a parsed contract; if structured access is needed, expose explicit accessors


# PLID-54 Security Boundaries & Hazardous Operations

Security guidance is most useful when it focuses on authority boundaries and high-risk actions rather than repeating the general misuse-resistance rules already covered by [PLID-11](#plid-11-meaningful-types--misuse-resistant-modeling) and [PLID-41](#plid-41-validation-safe-defaults--construction).

## PLID-54.01 Least-Privilege Surface Design (CRIT)

Prefer separate handles, clients, or permissions for materially different authority levels. Overpowered default interfaces increase blast radius and make misuse easier.

Examples:

- read
- write
- admin
- destructive maintenance

## PLID-54.02 Dangerous Operations Are Explicit (CRIT)

High-risk operations should require deliberate intent, not rely on subtle defaults or hidden side effects. Make destructive or irreversible actions obvious and hard to trigger accidentally.


# PLID-55 State Mutation & Side Effects

Many APIs are dangerous because mutation semantics are vague.

## PLID-55.01 Explicit Mutation Semantics (CRIT)

Document whether operations mutate receiver state, shared state, remote state, cache state, or only return derived values.

## PLID-55.02 Hidden Side Effects Prohibited (CRIT)

Avoid surprising writes, network calls, filesystem changes, telemetry emission, retries, or background jobs from harmless-looking methods.

## PLID-55.03 Idempotent vs Non-Idempotent Operations (MAJOR)

State clearly whether repeated calls are safe.


# PLID-56 Data Lifecycle & Retention

Especially relevant for SDKs / cloud libraries.

## PLID-56.01 Persistence Semantics (CRIT)

State whether data is ephemeral, cached, durable, replicated, queued, or eventually consistent.

## PLID-56.02 Deletion Semantics (CRIT)

Define whether delete means:

- hard delete
- soft delete
- tombstone
- async deletion
- retention delayed deletion

## PLID-56.03 Read-After-Write Guarantees (MAJOR)

Consumers need to know whether writes are immediately observable.


# Minimal Review/Approval Checklist

- public surface is intentional and inventoried
- stability tier is declared for each feature and feature flag
- names, conversions, and accessors follow ecosystem conventions
- types communicate meaning; internal generics and bounds are not leaked
- configuration validates early and ownership/allocation is caller-controlled where reasonable
- errors are actionable and structured; panics and unchecked failures are documented
- concurrency, performance, and cleanup/release behavior are documented
- extension points are intentionally sealed or intentionally open
- docs include entry-point overview, item-level docs, and verified examples
- debug/display representations are informative and redact sensitive data
- compatibility, migration, and changelog entries are complete
- safe defaults are sane, least-privilege is preserved, and dangerous operations are explicit
- wire contracts remain stable where promised

# References

- Joshua Bloch — *How to Design a Good API and Why It Matters* ([PDF](https://static.googleusercontent.com/media/research.google.com/en//pubs/archive/32713.pdf), [InfoQ article](https://www.infoq.com/articles/API-Design-Joshua-Bloch/))
- Rust API Guidelines — <https://rust-lang.github.io/api-guidelines/about.html>
- Elegant APIs in Rust (Pascal Hertleif) — <https://deterministic.space/elegant-apis-in-rust.html>
- .NET Framework Design Guidelines — <https://learn.microsoft.com/en-us/dotnet/standard/design-guidelines/>
- PEP 387 — Backwards Compatibility Policy (Python) — <https://peps.python.org/pep-0387/>
- Fail-fast systems — <https://en.wikipedia.org/wiki/Fail-fast_system>
