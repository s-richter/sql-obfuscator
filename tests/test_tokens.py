"""Tokenizing with sqlglot's command mode switched off."""

import pytest
import sqlglot
from sqlglot.tokens import TokenType

from sql_obfuscator.tokens import Dialect, source_text, tokenize

SWALLOWING_STATEMENTS = [
    (Dialect.TSQL, "GO\nSELECT a FROM secret_table"),
    (Dialect.TSQL, "PRINT 'x' SELECT a FROM secret_table"),
    (Dialect.TSQL, "FETCH NEXT FROM secret_table INTO @id"),
    (Dialect.HIVE, "MSCK REPAIR TABLE db.secret_table"),
    (Dialect.HIVE, "SHOW PARTITIONS db.secret_table"),
]


@pytest.mark.parametrize(("dialect", "sql"), SWALLOWING_STATEMENTS)
def test_a_name_after_a_command_word_is_its_own_token(dialect: Dialect, sql: str):
    names = [t.text for t in tokenize(sql, dialect) if t.token_type == TokenType.VAR]
    assert "secret_table" in names


@pytest.mark.parametrize(("dialect", "sql"), SWALLOWING_STATEMENTS)
def test_no_string_token_contains_the_rest_of_the_statement(dialect: Dialect, sql: str):
    strings = [t.text for t in tokenize(sql, dialect) if t.token_type == TokenType.STRING]
    assert not [s for s in strings if "secret_table" in s]


@pytest.mark.parametrize(("dialect", "sql"), SWALLOWING_STATEMENTS)
def test_stock_sqlglot_does_swallow_these(dialect: Dialect, sql: str):
    """The reason this module exists. If this fails, sqlglot changed; revisit ADR 0001."""
    strings = [
        t.text
        for t in sqlglot.tokenize(sql, read=dialect.value)
        if t.token_type == TokenType.STRING
    ]
    assert [s for s in strings if "secret_table" in s]


def test_comments_are_not_tokens():
    tokens = tokenize("SELECT a -- about secret_table\nFROM t /* more */", Dialect.TSQL)
    assert [t.text for t in tokens] == ["SELECT", "a", "FROM", "t"]


def test_nested_block_comment_is_one_comment_in_tsql():
    tokens = tokenize("SELECT a /* outer /* inner */ still outer */ FROM t", Dialect.TSQL)
    assert [t.text for t in tokens] == ["SELECT", "a", "FROM", "t"]


def test_comment_like_text_in_a_string_stays_a_string():
    tokens = tokenize("SELECT '-- not a comment' FROM t", Dialect.TSQL)
    assert tokens[1].token_type == TokenType.STRING
    assert tokens[1].text == "-- not a comment"


def test_hive_decodes_string_escapes_but_preserves_the_raw_source_span():
    sql = r"SELECT 'a\tb', 'atb'"

    tokens = tokenize(sql, Dialect.HIVE)

    assert tokens[1].text == "a\tb"
    assert tokens[3].text == "atb"
    assert source_text(sql, tokens[1]) == r"'a\tb'"
    assert source_text(sql, tokens[3]) == "'atb'"


def test_tsql_does_not_decode_hive_style_string_escapes():
    sql = r"SELECT 'a\tb'"

    token = tokenize(sql, Dialect.TSQL)[1]

    assert token.text == r"a\tb"
    assert source_text(sql, token) == r"'a\tb'"


def test_hive_identifier_can_start_with_digits():
    tokens = tokenize("SELECT 123secret FROM records", Dialect.HIVE)

    assert [(token.token_type, token.text) for token in tokens] == [
        (TokenType.SELECT, "SELECT"),
        (TokenType.VAR, "123secret"),
        (TokenType.FROM, "FROM"),
        (TokenType.VAR, "records"),
    ]


def test_tsql_splits_a_digit_prefixed_name():
    tokens = tokenize("SELECT 123secret FROM records", Dialect.TSQL)

    assert [(token.token_type, token.text) for token in tokens[1:3]] == [
        (TokenType.NUMBER, "123"),
        (TokenType.VAR, "secret"),
    ]
