from __future__ import annotations

import random
import re
from pathlib import Path
from typing import Callable


IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _load_reserved_keywords(filename: str) -> set[str]:
    path = Path(__file__).with_name(filename)
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise RuntimeError(
            f"Unable to load reserved keywords from: {path}") from exc

    keywords = {line.strip().lower() for line in lines if line.strip()}
    if not keywords:
        raise RuntimeError(f"Reserved keywords file is empty: {path}")
    return keywords


TSQL_RESERVED_KEYWORDS = _load_reserved_keywords("tsql_reserved_keywords.txt")


def build_identifier_safety_checker(
    *,
    keywords_file: str,
    identifier_re: re.Pattern[str] = IDENTIFIER_RE,
) -> Callable[[str], bool]:
    reserved_keywords = _load_reserved_keywords(keywords_file)

    def _is_safe(value: str) -> bool:
        if not value:
            return False
        if not identifier_re.fullmatch(value):
            return False
        return value.lower() not in reserved_keywords

    return _is_safe


_is_safe_identifier = build_identifier_safety_checker(keywords_file="tsql_reserved_keywords.txt")


def bracket_if_needed(value: str) -> str:
    """Bracket an identifier if it's not a safe bare identifier.

    This ensures syntactic validity in T-SQL even if a name
    is a reserved keyword or contains special characters.
    """
    if _is_safe_identifier(value):
        return value
    # Escape any brackets in the value by doubling them
    escaped = value.replace("]", "]]")
    return f"[{escaped}]"


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
    """Generates unique animal-based names.

    All generated names are guaranteed to be safe T-SQL identifiers
    (not reserved keywords and matching valid identifier syntax).
    """

    def __init__(
        self,
        seed: int | None = None,
        *,
        is_safe_identifier: Callable[[str], bool] = _is_safe_identifier,
    ) -> None:
        self._is_safe_identifier = is_safe_identifier
        self._rng = random.Random(seed)
        self._available = ANIMALS.copy()
        self._rng.shuffle(self._available)
        self._safe_bases = [
            name for name in ANIMALS if self._is_safe_identifier(name)]
        self._used: set[str] = set()
        self._suffix_counter: dict[str, int] = {}

    def next_name(self) -> str:
        """Generate next unique safe identifier name.

        Returns:
            A bare identifier string (not bracketed). Since all names
            are pre-filtered for safety, bracketing is not needed.

        Raises:
            RuntimeError: If all animal names are exhausted and no
                safe base is available for suffixed fallback.
        """
        while self._available:
            candidate = self._available.pop()
            if not self._is_safe_identifier(candidate):
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
        while candidate in self._used or not self._is_safe_identifier(candidate):
            self._suffix_counter[base] += 1
            candidate = f"{base}{self._suffix_counter[base]}"
        self._used.add(candidate)
        return candidate
