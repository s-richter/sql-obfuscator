"""The word lists that fake names are built from, such as ``frozen_lion``."""

from importlib.resources import files


def _load(name: str) -> tuple[str, ...]:
    text = files("sql_obfuscator.wordlists").joinpath(f"{name}.txt").read_text(encoding="utf-8")
    return tuple(text.split())


ADJECTIVES: tuple[str, ...] = _load("adjectives")
ANIMALS: tuple[str, ...] = _load("animals")
