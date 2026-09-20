#!/usr/bin/env python3
"""Extract every fenced ```plantuml block from diagrams/PlantUML.md into
standalone .puml files so they can be rendered and validated in CI.

Usage:
    python3 ci/extract_plantuml.py [--out DIR] [SOURCE.md]

Only *complete* diagrams are emitted: a fenced block counts as a diagram when it
contains an @startuml/@enduml pair. PlantUML.md also uses ```plantuml fences for
configuration fragments (bare `skinparam` runs, a `rectangle { ... }` shape
sketch). Those are illustrative snippets, not diagrams — rendering them fails,
and a render job that fails on its own documentation is a job that gets disabled.
Fragments are counted and reported so a real diagram cannot go missing unnoticed.

Each emitted block is written as out/diagram-<N>.puml, numbered in document order.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

FENCE_RE = re.compile(r"^```plantuml\s*$")
FENCE_END_RE = re.compile(r"^```\s*$")

DEFAULT_SOURCE = Path("diagrams/PlantUML.md")
DEFAULT_OUT = Path("ci/plantuml-render/out")


def extract_blocks(text: str) -> list[str]:
    lines = text.splitlines()
    blocks: list[str] = []
    in_block = False
    current: list[str] = []

    for line in lines:
        if not in_block and FENCE_RE.match(line):
            in_block = True
            current = []
            continue
        if in_block and FENCE_END_RE.match(line):
            in_block = False
            blocks.append("\n".join(current) + "\n")
            continue
        if in_block:
            current.append(line)

    if in_block:
        raise ValueError("Unterminated ```plantuml fence — no closing ``` found.")

    return blocks


# Element declarations: `component [Name] as alias`, `database "Name" as alias`, etc.
DECL_RE = re.compile(
    r"^\s*(?:component|database|node|cloud|queue|actor|folder|frame|storage|artifact"
    r"|interface|rectangle|package)\s+(?:\[[^\]]*\]|\"[^\"]*\")\s+as\s+([A-Za-z_]\w*)",
    re.M,
)
# Bare declarations without an `as`: `component alias`.
BARE_DECL_RE = re.compile(
    r"^\s*(?:component|database|node|cloud|queue|actor|folder|frame|storage|artifact"
    r"|interface)\s+([A-Za-z_]\w*)\s*$",
    re.M,
)
# Arrows between two plain aliases, covering -->, ==>, ..>, -[dotted]down->, ~~down~~> …
ARROW_RE = re.compile(
    r"^\s*([A-Za-z_]\w*)\s*"          # source alias
    r"(?:[-=.~][^\s]*?)"              # arrow body, any style
    r"(?:>|\|>)\s+"                   # arrow head
    r"([A-Za-z_]\w*)\b",              # target alias
    re.M,
)


def check_declared_aliases(block: str, index: int) -> list[str]:
    """Report arrow endpoints that were never declared.

    PlantUML silently auto-creates an undeclared alias and still exits 0, so a plain
    render check cannot catch this. That is exactly how the dark-theme template shipped
    an arrow to a `storage_c2` that no longer existed, giving everyone who copied the
    template a stray unstyled box. Verified against PlantUML 1.2026.8: the undeclared
    node renders cleanly and `-failfast2` does not complain.
    """
    declared = set(DECL_RE.findall(block)) | set(BARE_DECL_RE.findall(block))
    problems = []
    for source, target in ARROW_RE.findall(block):
        for alias in (source, target):
            if alias not in declared:
                problems.append(
                    f"diagram {index}: arrow endpoint '{alias}' is never declared — "
                    "PlantUML will invent an unstyled node for it"
                )
    return sorted(set(problems))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", nargs="?", default=str(DEFAULT_SOURCE))
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    args = parser.parse_args()

    source = Path(args.source)
    out_dir = Path(args.out)

    text = source.read_text(encoding="utf-8")
    blocks = extract_blocks(text)

    if not blocks:
        print(f"No ```plantuml blocks found in {source}", file=sys.stderr)
        return 1

    diagrams, fragments = [], 0
    for block in blocks:
        if "@startuml" in block and "@enduml" in block:
            diagrams.append(block)
        elif "@startuml" in block or "@enduml" in block:
            print(
                f"{source}: a plantuml block has @startuml without @enduml (or the "
                "reverse) — an unbalanced diagram cannot render",
                file=sys.stderr,
            )
            return 1
        else:
            fragments += 1

    if not diagrams:
        print(f"No complete @startuml diagrams found in {source}", file=sys.stderr)
        return 1

    undeclared: list[str] = []
    for index, block in enumerate(diagrams, start=1):
        undeclared.extend(check_declared_aliases(block, index))
    if undeclared:
        print(f"{source}: undeclared arrow endpoints", file=sys.stderr)
        for problem in undeclared:
            print(f"  {problem}", file=sys.stderr)
        return 1

    out_dir.mkdir(parents=True, exist_ok=True)
    for existing in out_dir.glob("diagram-*.puml"):
        existing.unlink()

    for index, block in enumerate(diagrams, start=1):
        target = out_dir / f"diagram-{index}.puml"
        target.write_text(block, encoding="utf-8")

    print(
        f"Extracted {len(diagrams)} complete diagram(s) from {source} into {out_dir}/ "
        f"({fragments} configuration fragment(s) skipped)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
