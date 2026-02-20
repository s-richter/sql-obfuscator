from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from sqlglot import exp


@dataclass(frozen=True)
class NormalizedIdentifier:
    value: str
    temp_prefix: str = ""
    original_unquoted: str = ""
    original_was_quoted: bool = False


class DialectProfile(Protocol):
    name: str
    sqlglot_dialect: str

    def split_batches(self, script: str) -> list[str]:
        ...

    def join_batches(self, batches: list[str]) -> str:
        ...

    def normalize_identifier(self, raw: str) -> NormalizedIdentifier:
        ...

    def is_safe_identifier(self, value: str) -> bool:
        ...

    def table_identifier_raw(self, identifier: exp.Identifier) -> str:
        ...

    def table_identifier_ast_value(self, value: str) -> str:
        ...

    def apply_original_quoting(
        self,
        identifier: exp.Identifier,
        *,
        original_unquoted: str,
        original_was_quoted: bool,
    ) -> None:
        ...
