"""The word lists can be used as SQL names without surprises."""

import re

import pytest
from sqlglot.dialects.dialect import Dialect as SqlglotDialect
from sqlglot.tokens import TokenType

from sql_obfuscator.tokens import Dialect, tokenize
from sql_obfuscator.words import ADJECTIVES, ANIMALS

LISTS = {"adjectives": ADJECTIVES, "animals": ANIMALS}

# Words that look like they describe data would mislead an LLM reading an obfuscated script.
MISLEADING = {
    "active", "current", "daily", "final", "first", "gross", "last", "main", "net", "new",
    "old", "primary", "raw", "temp", "total", "valid", "bronze", "silver", "gold", "golden",
}  # fmt: skip


@pytest.mark.parametrize("name", LISTS)
def test_words_are_plain_lowercase_and_sorted_without_duplicates(name: str):
    words = LISTS[name]
    assert all(re.fullmatch(r"[a-z]{3,12}", word) for word in words)
    assert list(words) == sorted(set(words))


def test_lists_do_not_overlap():
    assert not set(ADJECTIVES) & set(ANIMALS)


def test_there_are_enough_pairs_for_a_large_workspace():
    assert len(ADJECTIVES) * len(ANIMALS) >= 50_000


def test_no_word_suggests_a_meaning_for_the_data():
    assert not (set(ADJECTIVES) | set(ANIMALS)) & MISLEADING


@pytest.mark.parametrize("dialect", Dialect)
def test_no_word_is_a_keyword_or_built_in_function(dialect: Dialect):
    functions = {
        name.lower() for name in SqlglotDialect.get_or_raise(dialect.value).parser_class.FUNCTIONS
    }
    clashes = []
    for word in (*ADJECTIVES, *ANIMALS):
        tokens = tokenize(word, dialect)
        is_plain_name = len(tokens) == 1 and tokens[0].token_type == TokenType.VAR
        if not is_plain_name or word in functions:
            clashes.append(word)
    assert not clashes
