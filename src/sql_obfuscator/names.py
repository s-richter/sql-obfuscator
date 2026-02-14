from __future__ import annotations

import random
import re
from pathlib import Path


IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _load_tsql_reserved_keywords() -> set[str]:
    path = Path(__file__).with_name("tsql_reserved_keywords.txt")
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise RuntimeError(
            f"Unable to load TSQL reserved keywords from: {path}") from exc

    keywords = {line.strip().lower() for line in lines if line.strip()}
    if not keywords:
        raise RuntimeError(f"TSQL reserved keywords file is empty: {path}")
    return keywords


TSQL_RESERVED_KEYWORDS = _load_tsql_reserved_keywords()


def _is_safe_identifier(value: str) -> bool:
    if not value:
        return False
    if not IDENTIFIER_RE.fullmatch(value):
        return False
    return value.lower() not in TSQL_RESERVED_KEYWORDS


def _load_animals() -> list[str]:
    path = Path(__file__).with_name("identifier_replacements.txt")
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise RuntimeError(
            f"Unable to load identifier replacements from: {path}") from exc

    animals = [line.strip() for line in lines if line.strip()]
    if not animals:
        raise RuntimeError(f"Identifier replacements file is empty: {path}")
    return animals


ANIMALS = _load_animals()


class AnimalNameProvider:
    """Generates unique animal-based names."""

    def __init__(self, seed: int | None = None) -> None:
        self._rng = random.Random(seed)
        self._available = ANIMALS.copy()
        self._rng.shuffle(self._available)
        self._safe_bases = [
            name for name in ANIMALS if _is_safe_identifier(name)]
        self._used: set[str] = set()
        self._suffix_counter: dict[str, int] = {}

    def next_name(self) -> str:
        while self._available:
            candidate = self._available.pop()
            if not _is_safe_identifier(candidate):
                continue
            if candidate in self._used:
                continue
            self._used.add(candidate)
            return candidate

        if not self._safe_bases:
            raise RuntimeError(
                "No safe identifier replacements available. "
                "Update identifier_replacements.txt with valid non-keyword names."
            )

        base = self._rng.choice(self._safe_bases)
        self._suffix_counter[base] = self._suffix_counter.get(base, 1) + 1
        candidate = f"{base}{self._suffix_counter[base]}"
        while candidate in self._used or not _is_safe_identifier(candidate):
            self._suffix_counter[base] += 1
            candidate = f"{base}{self._suffix_counter[base]}"
        self._used.add(candidate)
        return candidate
