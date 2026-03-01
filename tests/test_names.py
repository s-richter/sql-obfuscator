import pytest

from sql_obfuscator import names


def test_next_name_skips_reserved_keyword(monkeypatch):
    monkeypatch.setattr(names, "ADJECTIVES", ["select"])
    monkeypatch.setattr(names, "ANIMALS", ["lion"])
    provider = names.CompositeNameProvider(seed=1)
    assert provider.next_name() == "select_lion"


def test_next_name_skips_invalid_identifier(monkeypatch):
    monkeypatch.setattr(names, "ADJECTIVES", ["clear", "sea-bad"])
    monkeypatch.setattr(names, "ANIMALS", ["otter"])
    provider = names.CompositeNameProvider(seed=1)
    assert provider.next_name() == "clear_otter"


def test_fallback_suffix_uses_safe_identifier(monkeypatch):
    monkeypatch.setattr(names, "ADJECTIVES", ["plain"])
    monkeypatch.setattr(names, "ANIMALS", ["lion"])
    provider = names.CompositeNameProvider(seed=1)
    assert provider.next_name() == "plain_lion"
    assert provider.next_name().startswith("plain_lion")
    assert provider.next_name() != "plain_lion"


def test_raises_when_no_safe_candidates(monkeypatch):
    monkeypatch.setattr(names, "ADJECTIVES", ["1bad", "sea-bad"])
    monkeypatch.setattr(names, "ANIMALS", ["otter"])
    provider = names.CompositeNameProvider(seed=1)
    with pytest.raises(RuntimeError, match="No safe identifier replacements"):
        provider.next_name()
