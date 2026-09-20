# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adopts [Semantic Versioning](https://semver.org/) tags so
consumers can pin a submodule (see README.md §How to Adopt) to a release
instead of tracking `main`.

## [Unreleased]

### Fixed

- Corrected every adoption path pointing at the old `cyberfabric` GitHub
  organization; the repository now lives at `constructorfabric/DNA`.
- Corrected the RateLimit reference: RFC 9239 does not define a RateLimit
  header; replaced with the `draft-ietf-httpapi-ratelimit-headers` link,
  pinned at revision 11.
- Reconciled the `.cursorrules`/`.windsurfrules` AI configs with the core
  guidelines on identifier format (canonical lowercase hyphenated UUIDv7) and
  `Idempotency-Key` obligation strength (clients SHOULD send, servers MUST
  honour).

### Added

- A "Conventions" section documenting RFC 2119 / RFC 8174 requirement-keyword
  usage across the corpus.
- `README.md` §Start Here now lists every document in the repository, closing
  the gap where roughly 40% of the corpus was unreachable from the entry
  point.
- `SECURITY.md`, `CODE_OF_CONDUCT.md`, and `.github/ISSUE_TEMPLATE/` for
  repository governance.
- Five required CI checks: DCO sign-off, Markdown link checking, Rust example
  compilation, Markdown linting, and PlantUML diagram rendering — all failing
  the build on error.

### Changed

- `code-ranker.yml` now runs on `push` to `main` only, plus `pull_request`,
  instead of double-running on every PR.
- The PR template's honour-system checkboxes ("Code examples tested", "Links
  are valid") are replaced with items the new CI checks actually verify.
