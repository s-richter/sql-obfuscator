import pytest

from sql_obfuscator import names


def test_next_name_skips_reserved_keyword(monkeypatch):
    monkeypatch.setattr(names, "ANIMALS", ["select", "lion"])
    provider = names.AnimalNameProvider(seed=1)
    assert provider.next_name() == "lion"


def test_next_name_skips_invalid_identifier(monkeypatch):
    monkeypatch.setattr(names, "ANIMALS", ["1bad", "sea-lion", "otter"])
    provider = names.AnimalNameProvider(seed=1)
    assert provider.next_name() == "otter"


def test_fallback_suffix_uses_safe_identifier(monkeypatch):
    monkeypatch.setattr(names, "ANIMALS", ["select", "lion"])
    provider = names.AnimalNameProvider(seed=1)
    assert provider.next_name() == "lion"
    assert provider.next_name().startswith("lion")
    assert provider.next_name() != "select"


def test_raises_when_no_safe_candidates(monkeypatch):
    monkeypatch.setattr(names, "ANIMALS", ["select", "1bad", "sea-lion"])
    provider = names.AnimalNameProvider(seed=1)
    with pytest.raises(RuntimeError, match="No safe identifier replacements"):
        provider.next_name()
