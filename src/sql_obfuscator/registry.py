from __future__ import annotations

from dataclasses import dataclass

from .names import AnimalNameProvider


@dataclass(frozen=True)
class IdentifierKey:
    value: str
    temp_prefix: str = ""


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

    def get_or_create(self, raw_identifier: str) -> str:
        key = normalize_identifier(raw_identifier)
        if key not in self._map:
            self._map[key] = self._name_provider.next_name()
        return f"{key.temp_prefix}{self._map[key]}"
