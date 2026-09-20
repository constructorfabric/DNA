# Security Policy

## Scope

This repository contains **documentation only** — API guidelines, language guides, and
diagrams. It ships no runnable service and stores no user data. The realistic risk surface
is narrow but not zero:

- Malicious or unsafe content hidden in a code example (e.g. a snippet that, if copied
  verbatim, introduces a vulnerability in a consumer's codebase).
- Supply-chain risk in this repository's own CI (a compromised or unpinned GitHub Action).
- A malicious pull request attempting to smuggle harmful content into a merged guideline.

## Reporting a Vulnerability

Please **do not** open a public issue for a security concern. Instead, use GitHub's private
vulnerability reporting feature:

1. Go to the repository's **Security** tab.
2. Select **Report a vulnerability**.
3. Describe the issue, including the affected file(s) and, if applicable, a suggested fix.

This routes the report to maintainers privately, without disclosing it publicly before a fix
is available.

## Response Targets

- **Acknowledgement**: within 3 business days of the report being filed.
- **Resolution**: timeline depends on severity; because this repository is documentation
  only, most fixes are a direct edit and ship quickly once triaged.

## Disclosure

Once a fix is merged, the maintainers will coordinate with the reporter on disclosure timing
and credit, if desired.
