from __future__ import annotations

import random

ANIMALS = [
    "cat",
    "dog",
    "mouse",
    "lion",
    "tiger",
    "wolf",
    "bear",
    "eagle",
    "fox",
    "otter",
]


class AnimalNameProvider:
    """Generates unique animal-based names."""

    def __init__(self, seed: int | None = None) -> None:
        self._rng = random.Random(seed)
        self._available = ANIMALS.copy()
        self._rng.shuffle(self._available)
        self._used: set[str] = set()
        self._suffix_counter: dict[str, int] = {}

    def next_name(self) -> str:
        if self._available:
            candidate = self._available.pop()
            self._used.add(candidate)
            return candidate

        base = self._rng.choice(ANIMALS)
        self._suffix_counter[base] = self._suffix_counter.get(base, 1) + 1
        candidate = f"{base}{self._suffix_counter[base]}"
        while candidate in self._used:
            self._suffix_counter[base] += 1
            candidate = f"{base}{self._suffix_counter[base]}"
        self._used.add(candidate)
        return candidate
