#!/usr/bin/env python3
"""Verify that the examples in the DNA documents obey the norms the DNA documents state.

Every defect this checks for was found by hand in a review of this repository. Hand review
does not repeat; a check does. Run it locally with:

    python3 ci/verify_doc_examples.py

It exits non-zero on the first violation and prints file, line and what is wrong.

Checks are deliberately scoped to fenced code blocks, because prose legitimately quotes the
wrong form in order to forbid it (VERSIONING.md has to be able to write "`Deprecation: true`
is NOT valid"). The repository-wide checks at the end are the exceptions, and they carry
their own allow-lists.
"""

from __future__ import annotations

import base64
import hashlib
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent

# Documents that describe defects rather than demonstrating norms.
NARRATIVE_FILES = {"CHANGELOG.md"}

FENCE = re.compile(r"^```([A-Za-z0-9+-]*)\s*$")
CURSOR_TOKEN = re.compile(r"\beyJ[A-Za-z0-9_-]{40,}")
ISO_TIMESTAMP = re.compile(r"\b\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z\b")
PLACEHOLDER_ID = re.compile(r"\b01[A-HJ-NP-TV-Z][A-Z0-9]*\.\.\.")

failures: list[str] = []


def fail(path: pathlib.Path, line_no: int, message: str) -> None:
    failures.append(f"{path.relative_to(ROOT)}:{line_no}: {message}")


def iter_blocks(text: str):
    """Yield (language, start_line, [lines]) for each fenced block."""
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        m = FENCE.match(lines[i])
        if not m:
            i += 1
            continue
        lang, start, body = m.group(1).lower(), i + 1, []
        i += 1
        while i < len(lines) and not lines[i].startswith("```"):
            body.append(lines[i])
            i += 1
        i += 1
        yield lang, start, body


def b64url_decode(token: str) -> bytes:
    return base64.urlsafe_b64decode(token + "=" * (-len(token) % 4))


def check_cursor(path: pathlib.Path, line_no: int, token: str) -> None:
    """Every cursor in the corpus must be a well-formed v2 cursor (QUERYING.md)."""
    try:
        cursor = json.loads(b64url_decode(token))
    except Exception as exc:  # noqa: BLE001 - the message is the point
        fail(path, line_no, f"cursor token does not decode to JSON: {exc}")
        return

    if cursor.get("v") != 2:
        fail(path, line_no, f"cursor v={cursor.get('v')!r}, expected 2")
    if "o" in cursor:
        fail(path, line_no, "cursor carries 'o', removed in v2 (direction lives in 's')")
    for member in ("k", "s", "d", "f", "p"):
        if member not in cursor:
            fail(path, line_no, f"cursor is missing required member {member!r}")
    if cursor.get("d") not in ("next", "prev"):
        fail(path, line_no, f"cursor d={cursor.get('d')!r}, expected 'next' or 'prev'")

    sort_tokens = [t for t in str(cursor.get("s", "")).split(",") if t]
    if not sort_tokens:
        fail(path, line_no, "cursor 's' is empty")
    for tok in sort_tokens:
        if tok[0] not in "+-":
            fail(path, line_no, f"cursor sort token {tok!r} lacks an explicit +/- prefix")
    if len(cursor.get("k", [])) != len(sort_tokens):
        fail(
            path,
            line_no,
            f"cursor has {len(cursor.get('k', []))} key value(s) but "
            f"{len(sort_tokens)} sort token(s); they must correspond 1:1",
        )


def check_http_block(path: pathlib.Path, start: int, body: list[str]) -> None:
    for offset, line in enumerate(body):
        line_no = start + offset + 1
        if line.lower().startswith("trace_id:"):
            fail(
                path,
                line_no,
                "underscored HTTP header 'trace_id' — nginx drops these by default; "
                "the wire name is X-Trace-Id (API.md §16)",
            )
        if line.startswith("Deprecation:"):
            value = line.split(":", 1)[1].strip()
            if not re.fullmatch(r"@\d+", value):
                fail(
                    path,
                    line_no,
                    f"Deprecation: {value!r} — RFC 9745 defines a structured-field Date, "
                    "e.g. 'Deprecation: @1767225599'",
                )
        if line.startswith("Sunset:"):
            value = line.split(":", 1)[1].strip()
            m = re.fullmatch(
                r"(Mon|Tue|Wed|Thu|Fri|Sat|Sun), (\d{2}) (\w{3}) (\d{4}) "
                r"\d{2}:\d{2}:\d{2} GMT",
                value,
            )
            if not m:
                fail(path, line_no, f"Sunset: {value!r} is not an RFC 9110 HTTP-date")
            else:
                import datetime

                months = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()
                day, mon, year = int(m.group(2)), months.index(m.group(3)) + 1, int(m.group(4))
                actual = datetime.date(year, mon, day).strftime("%a")
                if actual != m.group(1):
                    fail(
                        path,
                        line_no,
                        f"Sunset weekday {m.group(1)} disagrees with the date "
                        f"({year}-{mon:02d}-{day:02d} is a {actual}); RFC 9110 §5.6.7 "
                        "requires agreement and strict parsers reject the mismatch",
                    )


def check_json_block(path: pathlib.Path, start: int, body: list[str]) -> None:
    for offset, line in enumerate(body):
        line_no = start + offset + 1
        for match in ISO_TIMESTAMP.finditer(line):
            fraction = match.group(1)
            if fraction is None or len(fraction) != 4:  # ".SSS" is a dot plus three digits
                fail(
                    path,
                    line_no,
                    f"response timestamp {match.group(0)!r} must carry exactly three "
                    "fractional digits (.SSS) — API.md §13",
                )
        if '"id"' in line and PLACEHOLDER_ID.search(line):
            fail(
                path,
                line_no,
                "identifier uses the '01J...' placeholder form; resource identifiers are "
                "lowercase hyphenated UUIDv7 (API.md §3)",
            )


def check_documented_hashes() -> None:
    """QUERYING.md defines f/p as sha256(normalized)[0:12]; the examples must obey it."""
    documented = {
        "active eq true": "96a792a01275",
        "status in ('in_progress','open')": "b7ee2f3564b6",
        "created_at,id,priority,status,title": "2e8f53a199b5",
        "id,status,title": "1d7554b6d3b3",
    }
    for source, expected in documented.items():
        actual = hashlib.sha256(source.encode()).hexdigest()[:12]
        if actual != expected:
            failures.append(
                f"cursor hash for {source!r} is documented as {expected} "
                f"but sha256(...)[0:12] is {actual}"
            )


def check_error_codes_registered(markdown: list[pathlib.Path]) -> None:
    """Every top-level Problem Details `code` used in an example must be in the registry.

    Field-level `errors[].code` values are lowercase (`format`, `range`) and are deliberately
    not part of the registry, so matching on SCREAMING_SNAKE_CASE separates the two.
    """
    registry_path = ROOT / "REST" / "STATUS_CODES.md"
    if not registry_path.exists():
        failures.append("REST/STATUS_CODES.md is missing — it is the error code registry")
        return
    registry = set(re.findall(r"`([A-Z][A-Z0-9_]{2,})`", registry_path.read_text()))

    used = re.compile(r'"code"\s*:\s*"([A-Z][A-Z0-9_]{2,})"')
    for path in markdown:
        if path.name in NARRATIVE_FILES or path == registry_path:
            continue
        for line_no, line in enumerate(path.read_text().splitlines(), 1):
            for code in used.findall(line):
                if code not in registry:
                    fail(
                        path,
                        line_no,
                        f"Problem Details code {code!r} is not registered in "
                        "REST/STATUS_CODES.md — the catalogue must be complete",
                    )


def check_no_dead_org_urls(markdown: list[pathlib.Path]) -> None:
    """The GitHub organization is constructorfabric; cyberfabric is its former name."""
    for path in markdown:
        if path.name in NARRATIVE_FILES:
            continue
        for line_no, line in enumerate(path.read_text().splitlines(), 1):
            if "cyberfabric" in line.lower():
                fail(path, line_no, "references the retired 'cyberfabric' organization")


def check_no_orphan_documents(markdown: list[pathlib.Path]) -> None:
    """Every document must be reachable from README.md (CONTRIBUTING's 'no orphans' rule)."""
    readme = ROOT / "README.md"
    if not readme.exists():
        failures.append("README.md is missing")
        return
    linked = readme.read_text()
    exempt = {"README.md", "CHANGELOG.md", "SECURITY.md", "CODE_OF_CONDUCT.md"}
    for path in markdown:
        rel = path.relative_to(ROOT)
        if rel.name in exempt or rel.parts[0] in (".github", "ci", "schemas"):
            continue
        if rel.name not in linked:
            failures.append(
                f"{rel}: not linked from README.md — an unlinked document is an orphan "
                "(CONTRIBUTING.md, PR scope rules)"
            )


def main() -> int:
    markdown = sorted(
        p
        for p in ROOT.rglob("*.md")
        if ".claude" not in p.relative_to(ROOT).parts
        and "node_modules" not in p.relative_to(ROOT).parts
    )
    if not markdown:
        print("no markdown files found — is this the repository root?", file=sys.stderr)
        return 2

    cursors_seen = 0
    for path in markdown:
        text = path.read_text()
        for lang, start, body in iter_blocks(text):
            if lang == "http":
                check_http_block(path, start, body)
            if lang == "json":
                check_json_block(path, start, body)
        for line_no, line in enumerate(text.splitlines(), 1):
            for token in CURSOR_TOKEN.findall(line):
                cursors_seen += 1
                check_cursor(path, line_no, token)

    check_documented_hashes()
    check_error_codes_registered(markdown)
    check_no_dead_org_urls(markdown)
    check_no_orphan_documents(markdown)

    print(f"documents checked : {len(markdown)}")
    print(f"cursor tokens     : {cursors_seen}")

    if failures:
        print(f"\n{len(failures)} violation(s):\n")
        for failure in failures:
            print(f"  {failure}")
        return 1

    print("all document examples satisfy the norms they illustrate")
    return 0


if __name__ == "__main__":
    sys.exit(main())
