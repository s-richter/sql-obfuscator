from __future__ import annotations

from dataclasses import dataclass

from .names import AnimalNameProvider


@dataclass(frozen=True)
class IdentifierKey:
    value: str
    temp_prefix: str = ""


@dataclass
class MappingOccurrence:
    kind: str
    batch_index: int
    statement_index: int
    scope_id: str
    parent_kind: str
    role: str


@dataclass
class MappingEntry:
    key: IdentifierKey
    original_lexeme: str
    original_unbracketed: str
    original_was_bracketed: bool
    obfuscated_unbracketed: str
    occurrences: list[MappingOccurrence]


def normalize_identifier(raw: str) -> IdentifierKey:
    value = raw.strip()
    if value.startswith("[") and value.endswith("]") and len(value) >= 2:
        value = value[1:-1]

    temp_prefix = ""
    if value.startswith("##"):
        temp_prefix = "##"
        value = value[2:]
    elif value.startswith("#"):
        temp_prefix = "#"
        value = value[1:]

    return IdentifierKey(value=value.lower(), temp_prefix=temp_prefix)


class IdentifierRegistry:
    """Holds normalized original->obfuscated identifier mapping."""

    def __init__(self, seed: int | None = None) -> None:
        self._name_provider = AnimalNameProvider(seed=seed)
        self._map: dict[IdentifierKey, str] = {}
        self._entries: dict[IdentifierKey, MappingEntry] = {}

    def get_or_create(
        self,
        raw_identifier: str,
        *,
        kind: str = "identifier",
        batch_index: int = 0,
        statement_index: int = 0,
        scope_id: str = "",
        parent_kind: str = "",
        role: str = "",
    ) -> str:
        key = normalize_identifier(raw_identifier)
        if key not in self._map:
            self._map[key] = self._name_provider.next_name()
            original = raw_identifier.strip()
            self._entries[key] = MappingEntry(
                key=key,
                original_lexeme=original,
                original_unbracketed=_original_without_temp_prefix(original, key.temp_prefix),
                original_was_bracketed=_is_bracketed(original),
                obfuscated_unbracketed=self._map[key],
                occurrences=[],
            )

        self._entries[key].occurrences.append(
            MappingOccurrence(
                kind=kind,
                batch_index=batch_index,
                statement_index=statement_index,
                scope_id=scope_id,
                parent_kind=parent_kind,
                role=role,
            )
        )
        return f"{key.temp_prefix}{self._map[key]}"

    def mapping_payload(self) -> dict:
        entries = []
        forward_index: dict[str, str] = {}
        reverse_index: dict[str, dict[str, str]] = {}
        for key, entry in sorted(
            self._entries.items(), key=lambda item: (item[0].value, item[0].temp_prefix)
        ):
            obfuscated_lexeme = f"{key.temp_prefix}{entry.obfuscated_unbracketed}"
            forward_key = f"{key.temp_prefix}{key.value}"
            forward_index[forward_key] = obfuscated_lexeme
            reverse_index[obfuscated_lexeme] = {
                "normalized_original": key.value,
                "temp_prefix": key.temp_prefix,
            }
            entries.append(
                {
                    "normalized_original": key.value,
                    "temp_prefix": key.temp_prefix,
                    "original_lexeme": entry.original_lexeme,
                    "original_unbracketed": entry.original_unbracketed,
                    "original_was_bracketed": entry.original_was_bracketed,
                    "obfuscated_unbracketed": entry.obfuscated_unbracketed,
                    "obfuscated_lexeme": obfuscated_lexeme,
                    "occurrences": [
                        {
                            "kind": occ.kind,
                            "batch_index": occ.batch_index,
                            "statement_index": occ.statement_index,
                            "scope_id": occ.scope_id,
                            "parent_kind": occ.parent_kind,
                            "role": occ.role,
                        }
                        for occ in entry.occurrences
                    ],
                }
            )
        return {
            "schema_version": 1,
            "entries": entries,
            "forward_index": forward_index,
            "reverse_index": reverse_index,
        }


def _is_bracketed(value: str) -> bool:
    return value.startswith("[") and value.endswith("]") and len(value) >= 2


def _strip_outer_brackets(value: str) -> str:
    if _is_bracketed(value):
        return value[1:-1]
    return value


def _original_without_temp_prefix(value: str, temp_prefix: str) -> str:
    unbracketed = _strip_outer_brackets(value)
    if temp_prefix and unbracketed.startswith(temp_prefix):
        return unbracketed[len(temp_prefix):]
    return unbracketed
