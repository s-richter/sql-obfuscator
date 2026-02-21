from __future__ import annotations

from sql_obfuscator.translation import translate_sql, translate_sql_with_report


def test_translate_single_statement_success():
    sql = "SELECT [UserId] FROM [Users];"
    translated = translate_sql(
        sql,
        source_dialect="tsql",
        target_dialect="hive",
        pretty=True,
        validate=True,
    )
    assert "SELECT" in translated
    assert "UserId" in translated
    assert "Users" in translated


def test_translate_multi_batch_with_report_counts():
    sql = "SELECT [UserId] FROM [Users];\nGO\nSELECT [OrderId] FROM [Orders];"
    result = translate_sql_with_report(
        sql,
        source_dialect="tsql",
        target_dialect="hive",
        pretty=False,
        validate=True,
    )
    assert result.batch_count == 2
    assert result.statement_count == 2
    assert result.translated_statement_count == 2
    assert result.failed_statement_count == 0
    assert result.validated is True


def test_translate_empty_batch_passthrough_behavior():
    sql = "SELECT 1;\nGO\n\nGO\nSELECT 2;"
    result = translate_sql_with_report(
        sql,
        source_dialect="tsql",
        target_dialect="tsql",
        pretty=False,
        validate=False,
    )
    assert result.batch_count == 3
    assert result.statement_count == 2
    assert result.failed_statement_count == 0
    assert "\nGO\n\nGO\n" in result.output_sql


def test_translate_validation_toggle_behavior():
    sql = "SELECT 1;"
    without_validation = translate_sql_with_report(
        sql,
        source_dialect="hive",
        target_dialect="tsql",
        validate=False,
    )
    with_validation = translate_sql_with_report(
        sql,
        source_dialect="hive",
        target_dialect="tsql",
        validate=True,
    )
    assert without_validation.validated is False
    assert with_validation.validated is True


def test_translate_failure_record_structure_for_source_parse_error():
    sql = "SELECT (("
    result = translate_sql_with_report(
        sql,
        source_dialect="tsql",
        target_dialect="hive",
        validate=False,
    )
    assert result.failed_statement_count == 1
    failure = result.failures[0]
    assert failure["stage"] == "source_parse"
    assert failure["batch_index"] == 1
    assert failure["statement_index"] is None
    assert isinstance(failure["error"], str)
    assert isinstance(failure["snippet"], str)
