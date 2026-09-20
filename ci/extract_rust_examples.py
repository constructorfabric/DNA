#!/usr/bin/env python3
"""Extract fenced ```rust blocks from languages/RUST.md into a compilable crate.

Concatenates every fenced block whose info string is exactly `rust`, in
document order, and writes the result to ci/rust-examples/src/lib.rs. This is
the mechanism that enforces PLID-42.04 (Runnable & Verified Examples): if the
guide's snippets don't compile as one crate, this script's output won't
either, and `cargo check` catches it in CI.

Usage: python3 ci/extract_rust_examples.py
"""

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SOURCE_MD = REPO_ROOT / "languages" / "RUST.md"
OUTPUT_RS = REPO_ROOT / "ci" / "rust-examples" / "src" / "lib.rs"

FENCE_RE = re.compile(r"^```rust\s*$")
FENCE_END_RE = re.compile(r"^```\s*$")


def extract_blocks(markdown: str) -> list[str]:
    blocks = []
    lines = markdown.splitlines()
    in_block = False
    current: list[str] = []
    for line in lines:
        if not in_block and FENCE_RE.match(line):
            in_block = True
            current = []
            continue
        if in_block and FENCE_END_RE.match(line):
            in_block = False
            blocks.append("\n".join(current))
            continue
        if in_block:
            current.append(line)
    return blocks


def main() -> int:
    if not SOURCE_MD.exists():
        print(f"error: source file not found: {SOURCE_MD}", file=sys.stderr)
        return 1

    markdown = SOURCE_MD.read_text(encoding="utf-8")
    blocks = extract_blocks(markdown)

    if not blocks:
        print(f"error: no ```rust fenced blocks found in {SOURCE_MD}", file=sys.stderr)
        return 1

    header = (
        "// GENERATED FILE — do not edit by hand.\n"
        f"// Extracted from {SOURCE_MD.relative_to(REPO_ROOT)} by "
        "ci/extract_rust_examples.py.\n"
        "// Regenerate with: python3 ci/extract_rust_examples.py\n"
        "#![allow(dead_code)]\n\n"
    )
    body = "\n\n".join(blocks) + "\n"

    OUTPUT_RS.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_RS.write_text(header + body, encoding="utf-8")

    print(f"extracted {len(blocks)} rust block(s) from {SOURCE_MD} -> {OUTPUT_RS}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
