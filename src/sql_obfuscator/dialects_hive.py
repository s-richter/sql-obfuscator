from __future__ import annotations

import re
from dataclasses import dataclass

from sqlglot import exp

from .dialects_base import DialectProfile, NormalizedIdentifier
from .names import build_identifier_safety_checker


_HIVE_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_HIVE_SAFE_IDENTIFIER = build_identifier_safety_checker(
    keywords_file="hive_reserved_keywords.txt",
    identifier_re=_HIVE_IDENTIFIER_RE,
)


@dataclass(frozen=True)
class HiveProfile(DialectProfile):
    name: str = "hive"
    sqlglot_dialect: str = "hive"

    def split_batches(self, script: str) -> list[str]:
        return [script]

    def join_batches(self, batches: list[str]) -> str:
        return "\n".join(batches)

    def normalize_identifier(self, raw: str) -> NormalizedIdentifier:
        value = raw.strip()
        was_quoted = value.startswith("`") and value.endswith("`") and len(value) >= 2
        if was_quoted:
            value = value[1:-1]
        return NormalizedIdentifier(
            value=value.lower(),
            temp_prefix="",
            original_unquoted=value,
            original_was_quoted=was_quoted,
        )

    def is_safe_identifier(self, value: str) -> bool:
        return _HIVE_SAFE_IDENTIFIER(value)

    def table_identifier_raw(self, identifier: exp.Identifier) -> str:
        return identifier.name

    def table_identifier_ast_value(self, value: str) -> str:
        return value

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
