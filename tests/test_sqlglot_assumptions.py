"""sqlglot behaviour that the design decisions rest on.

These tests pin what sqlglot does today. If one fails after a sqlglot upgrade, the library
changed: reread the decision record named in the test before adjusting anything.
"""

import logging

import pytest
import sqlglot
from sqlglot import exp
from sqlglot.errors import ParseError
from sqlglot.tokens import TokenType

from sql_obfuscator.tokens import Dialect, source_text, tokenize


def _format(sql: str) -> str:
    trees = sqlglot.parse(sql, read="tsql")
    return "; ".join(tree.sql(dialect="tsql") for tree in trees if tree)


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT 1\nGO\nSELECT 2",
        "IF @a = 1 BEGIN UPDATE t SET a = 2 END ELSE BEGIN UPDATE t SET a = 3 END",
        "THROW 50001, 'bad', 1",
    ],
)
def test_parser_rejects_common_procedural_tsql(sql: str):
    """ADR 0001: the parser cannot carry procedures."""
    with pytest.raises(ParseError):
        sqlglot.parse(sql, read="tsql")


def test_parser_falls_back_to_an_opaque_command_for_try_catch(caplog):
    """ADR 0001: names inside an unparsed region are invisible to the syntax tree."""
    with caplog.at_level(logging.WARNING, logger="sqlglot"):
        tree = sqlglot.parse_one(
            "BEGIN TRY SELECT a FROM secret_table END TRY BEGIN CATCH SELECT 1 END CATCH",
            read="tsql",
        )
    assert isinstance(tree, exp.Command)
    assert not list(tree.find_all(exp.Table))


@pytest.mark.parametrize(
    ("sql", "corrupted"),
    [
        ("IF @x IS NULL SET @x = 1", "IF @x IS NULL AS SET BEGIN @x = 1"),
        ("OPEN cur", "OPEN AS cur"),
        ("IF @a = 1 SELECT 1 ELSE SELECT 2", "IF @a = 1 BEGIN SELECT 1; ELSE BEGIN SELECT 2"),
        (
            "IF @a = 1 BEGIN DELETE FROM t WHERE a = 1 END",
            "IF @a = 1 BEGIN DELETE FROM t WHERE a = 1 AS END",
        ),
    ],
)
def test_parser_silently_rewrites_some_statements_into_invalid_sql(sql: str, corrupted: str):
    """ADR 0005: why formatting is limited to an allow-list of statement types."""
    assert _format(sql) == corrupted


def test_formatting_changes_more_than_whitespace():
    """ADR 0005: type-position INT normalization is allowed; alias rewrites need a new rule."""
    assert _format("SELECT CAST(a AS INT), Total = SUM(b) FROM t") == (
        "SELECT CAST(a AS INTEGER), SUM(b) AS Total FROM t"
    )


def test_create_table_ntext_is_silently_rewritten_to_varchar_max(caplog):
    """ADR 0005: even one allowed statement can undergo a structural type rewrite."""
    sql = "CREATE TABLE dbo.Documents (Body NTEXT)"

    with caplog.at_level(logging.WARNING, logger="sqlglot"):
        trees = sqlglot.parse(sql, read="tsql")
        emitted = "; ".join(tree.sql(dialect="tsql") for tree in trees if tree)

    assert len(trees) == 1
    assert isinstance(trees[0], exp.Create)
    assert trees[0].args["kind"] == "TABLE"
    assert not caplog.records
    assert emitted == "CREATE TABLE dbo.Documents (Body VARCHAR(MAX))"
    assert sqlglot.parse_one(emitted, read="tsql") != trees[0]


def test_ntext_and_text_have_equal_asts_and_token_type_sequences():
    """ADR 0005: raw token spelling distinguishes types that the AST does not."""
    ntext = "CREATE TABLE t (c NTEXT)"
    text = "CREATE TABLE t (c TEXT)"

    assert sqlglot.parse_one(ntext, read="tsql") == sqlglot.parse_one(text, read="tsql")
    assert [token.token_type for token in tokenize(ntext, Dialect.TSQL)] == [
        token.token_type for token in tokenize(text, Dialect.TSQL)
    ]
    assert [source_text(ntext, token) for token in tokenize(ntext, Dialect.TSQL)] != [
        source_text(text, token) for token in tokenize(text, Dialect.TSQL)
    ]


def test_hive_hint_is_a_single_token_that_hides_a_name():
    """Hazard for milestone 2: a name inside a hint is not a name token."""
    tokens = tokenize("SELECT /*+ MAPJOIN(b) */ a.x FROM a JOIN b ON a.k = b.k", Dialect.HIVE)
    hints = [t for t in tokens if t.token_type == TokenType.HINT]
    assert len(hints) == 1
    assert "MAPJOIN(b)" in hints[0].text


def test_tsql_money_value_is_split_into_a_name_and_a_number():
    """Hazard for milestone 1: `$1250.75` does not arrive as one number token."""
    tokens = tokenize("SELECT $1250.75", Dialect.TSQL)
    assert [(t.token_type, t.text) for t in tokens[1:]] == [
        (TokenType.VAR, "$1250"),
        (TokenType.DOT, "."),
        (TokenType.NUMBER, "75"),
    ]
