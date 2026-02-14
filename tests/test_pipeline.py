from __future__ import annotations

import pytest

from sql_obfuscator.errors import ParseScriptError
from sql_obfuscator.pipeline import obfuscate_sql


def test_parse_error_single_batch(capsys):
    invalid_sql = "SELECT (("  # Unclosed parentheses - will fail to parse
    with pytest.raises(ParseScriptError) as exc_info:
        obfuscate_sql(invalid_sql)

    error_msg = str(exc_info.value)
    assert "Parse error" in error_msg
    assert "batch 1" in error_msg


def test_parse_error_multiple_batches():
    # First batch valid, second batch invalid
    sql_with_batches = """
    SELECT UserId, UserName FROM Users;
    GO
    SELECT ((
    """
    with pytest.raises(ParseScriptError) as exc_info:
        obfuscate_sql(sql_with_batches)

    error_msg = str(exc_info.value)
    assert "batch 2" in error_msg
    assert "2/2" in error_msg


def test_valid_sql_with_multiple_batches():
    sql_with_batches = """
    SELECT UserId FROM Users;
    GO
    SELECT ProductId FROM Products;
    GO
    INSERT INTO logs VALUES (1);
    """
    result = obfuscate_sql(sql_with_batches)
    assert "SELECT" in result
    assert "INSERT" in result


def test_parse_error_includes_sql_snippet():
    long_invalid_sql = "SELECT (("
    with pytest.raises(ParseScriptError) as exc_info:
        obfuscate_sql(long_invalid_sql)

    error_msg = str(exc_info.value)
    # Should include SQL snippet and batch info
    assert "SQL:" in error_msg
    assert "batch" in error_msg


def test_pretty_output_is_multiline():
    sql = "SELECT UserId, UserName FROM Users WHERE Status = 1;"
    result = obfuscate_sql(sql, pretty=True, seed=1)

    assert "\n" in result
    assert "SELECT" in result


def test_pretty_is_default():
    sql = "SELECT UserId, UserName FROM Users WHERE Status = 1;"
    result = obfuscate_sql(sql, seed=1)

    assert "\n" in result


def test_no_pretty_output_is_compact():
    sql = "SELECT UserId, UserName FROM Users WHERE Status = 1;"
    result = obfuscate_sql(sql, pretty=False, seed=1)

    assert "\n" not in result
