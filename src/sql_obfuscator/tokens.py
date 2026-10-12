"""Tokenizing SQL the way the engine needs it.

sqlglot's tokenizer has a command mode: after words such as ``GO``, ``FETCH`` or ``PRINT``
it swallows the rest of the statement, up to the next semicolon, as one string token. A
swallowed region would be replaced as a single value or, with strings kept, pass through
unobfuscated. Everything in this project tokenizes through this module, which switches the
mode off. See docs/adr/0001-token-first-engine.md.
"""

from enum import StrEnum
from functools import cache

from sqlglot.dialects.dialect import Dialect as SqlglotDialect
from sqlglot.tokens import Token, TokenType


class Dialect(StrEnum):
    TSQL = "tsql"
    HIVE = "hive"


@cache
def _tokenizer_class(dialect: Dialect) -> type:
    base = SqlglotDialect.get_or_raise(dialect.value).tokenizer_class

    class WithoutCommandMode(base):
        COMMANDS: set[TokenType] = set()
        KEYWORDS = {
            word: TokenType.VAR if token_type == TokenType.COMMAND else token_type
            for word, token_type in base.KEYWORDS.items()
        }

    return WithoutCommandMode


def tokenize(sql: str, dialect: Dialect) -> list[Token]:
    """Split a script into tokens, never swallowing the rest of a statement."""
    return _tokenizer_class(dialect)().tokenize(sql)


def source_text(sql: str, token: Token) -> str:
    """The exact characters of ``sql`` that ``token`` was read from, quotes included."""
    return sql[token.start : token.end + 1]
