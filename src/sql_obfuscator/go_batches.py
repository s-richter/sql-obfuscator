from __future__ import annotations

import re

_GO_LINE_RE = re.compile(r"^\s*GO\s*$", re.IGNORECASE)


def split_batches(script: str) -> list[str]:
    """Split SQL script into batches on standalone GO lines."""
    batches: list[str] = []
    current_lines: list[str] = []

    for line in script.splitlines():
        if _GO_LINE_RE.match(line):
            batches.append("\n".join(current_lines))
            current_lines = []
            continue
        current_lines.append(line)

    batches.append("\n".join(current_lines))
    return batches


def join_batches(batches: list[str]) -> str:
    """Join transformed batches back with GO separators."""
    return "\nGO\n".join(batches)
