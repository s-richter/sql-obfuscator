from __future__ import annotations

import random
import re
from collections.abc import Iterable
from dataclasses import dataclass
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


def _read_word_list_path(path: Path, *, description: str) -> list[str]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise RuntimeError(
            f"Unable to load {description} from: {path}") from exc

    return [line.strip() for line in lines if line.strip()]


def _load_word_list_path(path: Path, *, description: str) -> list[str]:
    words = _read_word_list_path(path, description=description)
    if not words:
        raise RuntimeError(f"{description.capitalize()} file is empty: {path}")
    return words


def _load_word_list(filename: str, *, description: str) -> list[str]:
    return _load_word_list_path(Path(__file__).with_name(filename), description=description)


ADJECTIVES = _load_word_list(
    "identifier_adjectives.txt",
    description="identifier adjectives",
)
ANIMALS = _load_word_list(
    "identifier_replacements.txt",
    description="identifier replacements",
)


@dataclass(frozen=True)
class IdentifierVocabularyDiagnostic:
    severity: str
    code: str
    word_list: str
    message: str
    value: str | None = None


@dataclass(frozen=True)
class IdentifierVocabulary:
    adjectives: tuple[str, ...]
    replacements: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "adjectives", self._normalized_words(self.adjectives))
        object.__setattr__(self, "replacements", self._normalized_words(self.replacements))

    @classmethod
    def from_words(
        cls,
        *,
        adjectives: Iterable[str],
        replacements: Iterable[str],
    ) -> IdentifierVocabulary:
        return cls(
            adjectives=tuple(adjectives),
            replacements=tuple(replacements),
        )

    @classmethod
    def load(
        cls,
        *,
        adjectives_path: Path | None = None,
        replacements_path: Path | None = None,
    ) -> IdentifierVocabulary:
        return cls.from_words(
            adjectives=_read_word_list_path(
                adjectives_path or Path(__file__).with_name("identifier_adjectives.txt"),
                description="identifier adjectives",
            ),
            replacements=_read_word_list_path(
                replacements_path or Path(__file__).with_name("identifier_replacements.txt"),
                description="identifier replacements",
            ),
        )

    @property
    def pool_size(self) -> int:
        return len(self.adjectives) * len(self.replacements)

    def safe_pool_size(
        self,
        *,
        is_safe_identifier: Callable[[str], bool] = _is_safe_identifier,
    ) -> int:
        return len(
            {
                candidate
                for candidate in self._candidate_names()
                if is_safe_identifier(candidate)
            }
        )

    def validation_diagnostics(
        self,
        *,
        is_safe_identifier: Callable[[str], bool] = _is_safe_identifier,
    ) -> tuple[IdentifierVocabularyDiagnostic, ...]:
        diagnostics = [
            *self._word_list_diagnostics(
                "adjectives",
                self.adjectives,
                is_safe_identifier=is_safe_identifier,
            ),
            *self._word_list_diagnostics(
                "replacements",
                self.replacements,
                is_safe_identifier=is_safe_identifier,
            ),
        ]
        if self.safe_pool_size(is_safe_identifier=is_safe_identifier) == 0:
            diagnostics.append(
                IdentifierVocabularyDiagnostic(
                    severity="error",
                    code="vocabulary.no_safe_generated_names",
                    word_list="generated_names",
                    message="Vocabulary does not produce any safe generated identifiers.",
                )
            )
        return tuple(diagnostics)

    def is_valid(
        self,
        *,
        is_safe_identifier: Callable[[str], bool] = _is_safe_identifier,
    ) -> bool:
        return not any(
            diagnostic.severity == "error"
            for diagnostic in self.validation_diagnostics(
                is_safe_identifier=is_safe_identifier
            )
        )

    def sample_names(
        self,
        *,
        count: int = 5,
        seed: int | None = None,
        is_safe_identifier: Callable[[str], bool] = _is_safe_identifier,
    ) -> tuple[str, ...]:
        if count < 0:
            raise ValueError("Sample count must not be negative.")
        provider = self.create_provider(
            seed=seed,
            is_safe_identifier=is_safe_identifier,
        )
        return tuple(provider.next_name() for _ in range(count))

    def create_provider(
        self,
        *,
        seed: int | None = None,
        is_safe_identifier: Callable[[str], bool] = _is_safe_identifier,
    ) -> CompositeNameProvider:
        return CompositeNameProvider(
            seed=seed,
            is_safe_identifier=is_safe_identifier,
            vocabulary=self,
        )

    def _candidate_names(self) -> tuple[str, ...]:
        return tuple(
            f"{adjective}_{replacement}"
            for adjective in self.adjectives
            for replacement in self.replacements
        )

    @staticmethod
    def _normalized_words(words: Iterable[str]) -> tuple[str, ...]:
        return tuple(word.strip() for word in words if word.strip())

    @staticmethod
    def _word_list_diagnostics(
        word_list: str,
        words: tuple[str, ...],
        *,
        is_safe_identifier: Callable[[str], bool],
    ) -> list[IdentifierVocabularyDiagnostic]:
        diagnostics: list[IdentifierVocabularyDiagnostic] = []
        if not words:
            diagnostics.append(
                IdentifierVocabularyDiagnostic(
                    severity="error",
                    code="vocabulary.empty_word_list",
                    word_list=word_list,
                    message=f"Identifier {word_list} must contain at least one word.",
                )
            )
            return diagnostics

        seen: set[str] = set()
        for word in words:
            normalized = word.casefold()
            if normalized in seen:
                diagnostics.append(
                    IdentifierVocabularyDiagnostic(
                        severity="warning",
                        code="vocabulary.duplicate_word",
                        word_list=word_list,
                        value=word,
                        message=f"Duplicate identifier {word_list} entry: {word}",
                    )
                )
            seen.add(normalized)
            if not IDENTIFIER_RE.fullmatch(word):
                diagnostics.append(
                    IdentifierVocabularyDiagnostic(
                        severity="error",
                        code="vocabulary.invalid_identifier_shape",
                        word_list=word_list,
                        value=word,
                        message=f"Identifier {word_list} entry is not a safe word: {word}",
                    )
                )
            elif not is_safe_identifier(word):
                diagnostics.append(
                    IdentifierVocabularyDiagnostic(
                        severity="warning",
                        code="vocabulary.reserved_keyword",
                        word_list=word_list,
                        value=word,
                        message=f"Identifier {word_list} entry is a reserved keyword: {word}",
                    )
                )
        return diagnostics


def default_identifier_vocabulary() -> IdentifierVocabulary:
    return IdentifierVocabulary.from_words(
        adjectives=ADJECTIVES,
        replacements=ANIMALS,
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
        vocabulary: IdentifierVocabulary | None = None,
    ) -> None:
        self._is_safe_identifier = is_safe_identifier
        self._rng = random.Random(seed)
        self.vocabulary = vocabulary or default_identifier_vocabulary()
        self._available = list(self.vocabulary._candidate_names())
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
