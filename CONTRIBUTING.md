# Contributing to DNA (Development Norms & Architecture)

Thank you for your interest in contributing! This guide explains the minimal workflow for proposing changes via pull requests and the legal requirement to sign off your commits.

## 1) Legal: Developer Certificate of Origin (DCO)

This project uses the Developer Certificate of Origin (DCO) version 1.1.
- The DCO text is included in `DCO.txt` (Version 1.1). This is the current and widely adopted version; please keep it as 1.1.
- Every commit must include a Signed-off-by line to certify you have the right to submit the contribution under the project license (Apache-2.0).

Sign off your commits:
```bash
git commit -s -m "your message"
```
This adds a footer like:
```
Signed-off-by: Your Name <your.email@example.com>
```
Enable auto sign-off for all commits:
```bash
git config --global format.signoff true
```

## 2) Contribution Flow (Fork-based PRs)

1. Fork the repository (GitHub → Fork)
2. Add remotes locally (replace <org> with the upstream organization):
   ```bash
   git remote set-url origin git@github.com:myfork/DNA.git
   git remote add upstream git@github.com:constructorfabric/DNA.git
   git fetch upstream
   git checkout main && git reset --hard upstream/main
   ```
3. Create a topic branch from the up-to-date `upstream/main`:
   ```bash
   git checkout -b docs/<short-topic>
   ```
4. Make focused changes (keep PRs small and single-topic)
5. Commit with sign-off (`-s`) and descriptive message
6. Push the branch to your fork:
   ```bash
   git push -u origin docs/<short-topic>
   ```
7. Open a Pull Request from `myfork/DNA:docs/<short-topic>` to `upstream:main`

## 3) PR Scope & Structure

- One PR = one topic. Avoid mixing structural/spec changes with editorial or infrastructure changes.
- Keep diffs minimal; prefer multiple small PRs over one large one.
- If you change headings/anchors, update any in-document links accordingly.

Suggested categories:
- `ci/compliance`: DCO, workflows, PR templates
- `docs/api`: API guideline structure/content
- `docs/rust`: Rust best practices
- `docs/editorial`: terminology/formatting consistency

## 4) Commit Message Convention

Use clear, imperative summaries (max ~72 chars), optionally with a domain:
```
docs(api): unify section 6 and expand section 24
```
Add a multi-line body when needed to explain rationale, scope, and any nuances.

Always include DCO sign-off (`-s`).

## 5) PR Checklist

Before submitting your PR, please verify:
- [ ] All commits are signed off (DCO) with `git commit -s`
- [ ] The PR contains a single, focused topic
- [ ] Headings and anchors are consistent and linked correctly
- [ ] Examples are self-consistent and realistic
- [ ] No hard-coded dependency versions were introduced
- [ ] Spelling, grammar, and formatting are consistent

## 6) Review & Merge

- Automated checks (e.g., DCO) must pass
- A maintainer will review for clarity, scope, and alignment with DNA principles
- Address feedback via follow-up commits in the same branch
- Squash merge is recommended for documentation-only PRs

## 7) Licensing

By contributing, you agree your contribution will be licensed under the Apache License, Version 2.0. See `LICENSE` for details and `DCO.txt` (Version 1.1) for the certification text.

---

If you have questions, please open a discussion or draft PR to get early feedback.
