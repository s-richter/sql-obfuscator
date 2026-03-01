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


def _load_word_list(filename: str, *, description: str) -> list[str]:
    path = Path(__file__).with_name(filename)
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise RuntimeError(
            f"Unable to load {description} from: {path}") from exc

    words = [line.strip() for line in lines if line.strip()]
    if not words:
        raise RuntimeError(f"{description.capitalize()} file is empty: {path}")
    return words


ADJECTIVES = _load_word_list(
    "identifier_adjectives.txt",
    description="identifier adjectives",
)
ANIMALS = _load_word_list(
    "identifier_replacements.txt",
    description="identifier replacements",
)


class CompositeNameProvider:
    """Generates unique adjective-animal identifier names.

    All generated names are guaranteed to be safe identifiers for the
    configured dialect, or raise if no safe base names exist.
    """

    def __init__(
        self,
        seed: int | None = None,
        *,
        is_safe_identifier: Callable[[str], bool] = _is_safe_identifier,
    ) -> None:
        self._is_safe_identifier = is_safe_identifier
        self._rng = random.Random(seed)
        self._available = [
            f"{adjective}_{animal}"
            for adjective in ADJECTIVES
            for animal in ANIMALS
        ]
        self._rng.shuffle(self._available)
        self._safe_bases = [
            name for name in self._available if self._is_safe_identifier(name)
        ]
        self._used: set[str] = set()
        self._suffix_counter: dict[str, int] = {}

    def next_name(self) -> str:
        """Generate next unique safe identifier name.

        Returns:
            A bare identifier string (not bracketed). Since all names
            are pre-filtered for safety, bracketing is not needed.

        Raises:
            RuntimeError: If all base names are exhausted and no
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
                "Update identifier_adjectives.txt and identifier_replacements.txt "
                "with valid non-keyword names."
            )

        base = self._rng.choice(self._safe_bases)
        self._suffix_counter[base] = self._suffix_counter.get(base, 1) + 1
        candidate = f"{base}{self._suffix_counter[base]}"
        while candidate in self._used or not self._is_safe_identifier(candidate):
            self._suffix_counter[base] += 1
            candidate = f"{base}{self._suffix_counter[base]}"
        self._used.add(candidate)
        return candidate


AnimalNameProvider = CompositeNameProvider
