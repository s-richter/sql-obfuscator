"""The SQL test scripts are sound and the tokenizer reads every one of them faithfully."""

from sqlglot.tokens import TokenType

from sql_obfuscator.tokens import Dialect, source_text, tokenize
from tests.conftest import SCRIPTS_DIR, Script, all_scripts

STRING_TYPES = {TokenType.STRING, TokenType.NATIONAL_STRING}


def test_both_dialects_have_scripts():
    dialects = {script.dialect for script in all_scripts()}
    assert dialects == set(Dialect)


def test_every_script_is_described_in_the_overview():
    overview = (SCRIPTS_DIR / "README.md").read_text(encoding="utf-8")
    missing = [s.path.name for s in all_scripts() if f"`{s.path.name}`" not in overview]
    assert not missing, f"add these scripts to tests/scripts/README.md: {missing}"


def test_script_tokenizes_without_swallowed_regions(script: Script):
    tokens = tokenize(script.sql, script.dialect)
    assert tokens
    assert not [t for t in tokens if t.token_type == TokenType.COMMAND]


def test_token_positions_point_at_the_token_text(script: Script):
    """The engine rewrites a script by position, so positions must be exact."""
    sql = script.sql
    for token in tokenize(sql, script.dialect):
        text = source_text(sql, token)
        if token.token_type == TokenType.VAR:
            assert text == token.text
        elif token.token_type == TokenType.IDENTIFIER:
            assert text[0] in '[`"' and text[-1] in ']`"'
            assert text[1:-1].replace("]]", "]") == token.text
        elif token.token_type in STRING_TYPES:
            assert text[-1] in "'\"", f"string token does not end with a quote: {text!r}"


def test_only_whitespace_and_comments_lie_between_tokens(script: Script):
    """Whatever the tokenizer skips must be a comment, or it would pass through unseen."""
    sql = script.sql
    position = 0
    skipped = []
    for token in tokenize(sql, script.dialect):
        if token.start >= position:
            skipped.append(sql[position : token.start])
            position = token.end + 1
    skipped.append(sql[position:])
    unexpected = [
        gap.strip() for gap in skipped if gap.strip() and not gap.strip().startswith(("--", "/*"))
    ]
    assert not unexpected
