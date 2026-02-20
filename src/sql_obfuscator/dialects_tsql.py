from __future__ import annotations

import re
from dataclasses import dataclass

from sqlglot import exp

from .dialects_base import DialectProfile, NormalizedIdentifier
from .names import build_identifier_safety_checker


_GO_LINE_RE = re.compile(r"^\s*GO\s*$", re.IGNORECASE)
_TSQL_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_TSQL_SAFE_IDENTIFIER = build_identifier_safety_checker(
    keywords_file="tsql_reserved_keywords.txt",
    identifier_re=_TSQL_IDENTIFIER_RE,
)


@dataclass(frozen=True)
class TsqlProfile(DialectProfile):
    name: str = "tsql"
    sqlglot_dialect: str = "tsql"

    def split_batches(self, script: str) -> list[str]:
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

    def join_batches(self, batches: list[str]) -> str:
        return "\nGO\n".join(batches)

    def normalize_identifier(self, raw: str) -> NormalizedIdentifier:
        value = raw.strip()
        was_quoted = value.startswith("[") and value.endswith("]") and len(value) >= 2
        if was_quoted:
            value = value[1:-1]

        temp_prefix = ""
        if value.startswith("##"):
            temp_prefix = "##"
            value = value[2:]
        elif value.startswith("#"):
            temp_prefix = "#"
            value = value[1:]

        return NormalizedIdentifier(
            value=value.lower(),
            temp_prefix=temp_prefix,
            original_unquoted=value,
            original_was_quoted=was_quoted,
        )

    def is_safe_identifier(self, value: str) -> bool:
        return _TSQL_SAFE_IDENTIFIER(value)

    def table_identifier_raw(self, identifier: exp.Identifier) -> str:
        prefix = ""
        if identifier.args.get("global_"):
            prefix = "##"
        elif identifier.args.get("temporary"):
            prefix = "#"
        return f"{prefix}{identifier.name}"

    def table_identifier_ast_value(self, value: str) -> str:
        return value.lstrip("#")

    def apply_original_quoting(
        self,
        identifier: exp.Identifier,
        *,
        original_unquoted: str,
        original_was_quoted: bool,
    ) -> None:
        identifier.set("this", original_unquoted)
        if original_was_quoted:
            identifier.set("quoted", True)
