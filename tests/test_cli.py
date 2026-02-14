from __future__ import annotations

from pathlib import Path

from sql_obfuscator.cli import main


def test_cli_missing_file_returns_nonzero(capsys):
    rc = main(["does_not_exist.sql"])
    captured = capsys.readouterr()
    assert rc == 1
    assert "Error:" in captured.err


def test_cli_prints_output_for_valid_sql(tmp_path: Path, capsys):
    sql_file = tmp_path / "input.sql"
    sql_file.write_text("SELECT 1;", encoding="utf-8")

    rc = main([str(sql_file)])
    captured = capsys.readouterr()

    assert rc == 0
    assert "SELECT 1" in captured.out


def test_cli_parse_error_returns_nonzero_with_context(tmp_path: Path, capsys):
    sql_file = tmp_path / "invalid.sql"
    invalid_sql = "SELECT (("  # Unclosed parentheses - will fail to parse
    sql_file.write_text(invalid_sql, encoding="utf-8")

    rc = main([str(sql_file)])
    captured = capsys.readouterr()

    assert rc == 1
    assert "Error:" in captured.err
    assert "Parse error" in captured.err
    assert "batch" in captured.err


def test_cli_parse_error_in_batch_two(tmp_path: Path, capsys):
    sql_file = tmp_path / "multi_batch.sql"
    # First batch is valid, second batch has syntax error
    sql_content = "SELECT 1;\nGO\nSELECT (("
    sql_file.write_text(sql_content, encoding="utf-8")

    rc = main([str(sql_file)])
    captured = capsys.readouterr()

    assert rc == 1
    assert "Error:" in captured.err
    assert "batch 2" in captured.err
