from __future__ import annotations

from sql_obfuscator.redaction import apply_redaction, restore_reversible_redaction


def test_apply_redaction_none_mode_is_passthrough():
    sql = "SELECT 'secret', 42;"
    result = apply_redaction(
        sql,
        dialect="tsql",
        pretty=False,
        redact_literals=True,
        strip_comments=True,
        redaction_mode="none",
    )
    assert result.output_sql == sql
    assert result.redaction_payload is None


def test_apply_redaction_irreversible_replaces_literals_and_comments():
    sql = "SELECT 'secret' AS v -- comment\nFROM Users WHERE Score = 42;"
    result = apply_redaction(
        sql,
        dialect="tsql",
        pretty=True,
        redact_literals=True,
        strip_comments=True,
        redaction_mode="irreversible",
    )
    assert "<REDACTED_STR>" in result.output_sql
    assert "42" not in result.output_sql
    assert "comment" not in result.output_sql
    assert result.redaction_payload is None


def test_apply_redaction_reversible_emits_placeholders_and_payload():
    sql = "SELECT 'secret' AS s, 42 AS n;"
    result = apply_redaction(
        sql,
        dialect="tsql",
        pretty=False,
        redact_literals=True,
        strip_comments=False,
        redaction_mode="reversible",
    )
    assert "__SQL_OBFUSCATOR_STR_" in result.output_sql
    assert "90000000000" in result.output_sql
    assert result.redaction_payload is not None
    entries = result.redaction_payload["entries"]
    assert len(entries) == 2
    assert entries[0]["is_string"] is True
    assert entries[1]["is_string"] is False


def test_restore_reversible_redaction_restores_original_literals():
    sql = "SELECT 'secret' AS s, 42 AS n;"
    redacted = apply_redaction(
        sql,
        dialect="tsql",
        pretty=True,
        redact_literals=True,
        strip_comments=False,
        redaction_mode="reversible",
    )
    restored_sql, report = restore_reversible_redaction(
        redacted.output_sql,
        dialect="tsql",
        pretty=True,
        redaction_payload=redacted.redaction_payload or {},
    )
    assert "secret" in restored_sql
    assert "42" in restored_sql
    assert report["unknown_placeholder_count"] == 0
    assert report["missing_placeholder_count"] == 0


def test_restore_reversible_redaction_reports_unknown_and_missing():
    sql = "SELECT 'secret' AS s;"
    redacted = apply_redaction(
        sql,
        dialect="tsql",
        pretty=False,
        redact_literals=True,
        strip_comments=False,
        redaction_mode="reversible",
    )
    edited = redacted.output_sql.replace("__SQL_OBFUSCATOR_STR_000001__", "__SQL_OBFUSCATOR_STR_999999__", 1)
    restored_sql, report = restore_reversible_redaction(
        edited,
        dialect="tsql",
        pretty=False,
        redaction_payload=redacted.redaction_payload or {},
    )
    assert "__SQL_OBFUSCATOR_STR_999999__" in restored_sql
    assert report["unknown_placeholder_count"] == 1
    assert report["missing_placeholder_count"] == 1


def test_reversible_redaction_preserves_tsql_go_batch_structure():
    sql = "SELECT 'a';\nGO\nSELECT 7;"
    redacted = apply_redaction(
        sql,
        dialect="tsql",
        pretty=False,
        redact_literals=True,
        strip_comments=False,
        redaction_mode="reversible",
    )
    assert "\nGO\n" in redacted.output_sql
    restored_sql, report = restore_reversible_redaction(
        redacted.output_sql,
        dialect="tsql",
        pretty=False,
        redaction_payload=redacted.redaction_payload or {},
    )
    assert "a" in restored_sql
    assert "7" in restored_sql
    assert report["missing_placeholder_count"] == 0


def test_reversible_redaction_hive_roundtrip():
    sql = "SELECT 'hive_secret' AS s, 99 AS n FROM users"
    redacted = apply_redaction(
        sql,
        dialect="hive",
        pretty=False,
        redact_literals=True,
        strip_comments=False,
        redaction_mode="reversible",
    )
    restored_sql, report = restore_reversible_redaction(
        redacted.output_sql,
        dialect="hive",
        pretty=False,
        redaction_payload=redacted.redaction_payload or {},
    )
    assert "hive_secret" in restored_sql
    assert "99" in restored_sql
    assert report["unknown_placeholder_count"] == 0


def test_irreversible_redaction_handles_date_like_and_multiline_string_literals():
    sql = "SELECT '2024-01-01' AS d, 'line1\nline2' AS m, CAST('2020-02-29' AS DATE) AS c;"
    result = apply_redaction(
        sql,
        dialect="hive",
        pretty=True,
        redact_literals=True,
        strip_comments=False,
        redaction_mode="irreversible",
    )
    assert "2024-01-01" not in result.output_sql
    assert "2020-02-29" not in result.output_sql
    assert "line1" not in result.output_sql
    assert "<REDACTED_STR>" in result.output_sql


def test_irreversible_comment_stripping_handles_line_and_block_comments():
    sql = "SELECT 1 /* block secret */ AS n -- line secret\nFROM users;"
    result = apply_redaction(
        sql,
        dialect="tsql",
        pretty=True,
        redact_literals=False,
        strip_comments=True,
        redaction_mode="irreversible",
    )
    assert "block secret" not in result.output_sql
    assert "line secret" not in result.output_sql


def test_redaction_boolean_and_null_literals_current_behavior_is_preserved():
    sql = "SELECT TRUE AS t, FALSE AS f, NULL AS n"
    result = apply_redaction(
        sql,
        dialect="hive",
        pretty=False,
        redact_literals=True,
        strip_comments=False,
        redaction_mode="irreversible",
    )
    assert "TRUE" in result.output_sql
    assert "FALSE" in result.output_sql
    assert "NULL" in result.output_sql


def test_irreversible_redaction_skips_numeric_datatype_params():
    sql = "CREATE TABLE t (a NUMERIC(10,2)); SELECT * FROM t WHERE a = 42;"
    result = apply_redaction(
        sql,
        dialect="tsql",
        pretty=False,
        redact_literals=True,
        strip_comments=False,
        redaction_mode="irreversible",
    )
    assert "NUMERIC(10, 2)" in result.output_sql or "NUMERIC(10,2)" in result.output_sql
    assert " = 0" in result.output_sql
    assert " = 42" not in result.output_sql


def test_reversible_redaction_skips_numeric_datatype_params_and_restores_values():
    sql = "CREATE TABLE t (a NUMERIC(10,2)); SELECT * FROM t WHERE a = 42;"
    redacted = apply_redaction(
        sql,
        dialect="tsql",
        pretty=False,
        redact_literals=True,
        strip_comments=False,
        redaction_mode="reversible",
    )
    assert "NUMERIC(10, 2)" in redacted.output_sql or "NUMERIC(10,2)" in redacted.output_sql
    assert "900000000001" in redacted.output_sql
    restored_sql, report = restore_reversible_redaction(
        redacted.output_sql,
        dialect="tsql",
        pretty=False,
        redaction_payload=redacted.redaction_payload or {},
    )
    assert "NUMERIC(10, 2)" in restored_sql or "NUMERIC(10,2)" in restored_sql
    assert " = 42" in restored_sql
    assert report["missing_placeholder_count"] == 0


def test_strings_only_policy_redacts_only_strings():
    sql = "SELECT 'secret' AS s, 42 AS n;"
    result = apply_redaction(
        sql,
        dialect="tsql",
        pretty=False,
        redact_literals=True,
        strip_comments=False,
        redaction_mode="irreversible",
        redaction_policy="strings-only",
    )
    assert "<REDACTED_STR>" in result.output_sql
    assert "42" in result.output_sql


def test_sensitive_policy_redacts_only_configured_column_literals():
    sql = "SELECT * FROM users WHERE email = 'a@b.com' AND status = 'active' AND score = 42;"
    result = apply_redaction(
        sql,
        dialect="tsql",
        pretty=False,
        redact_literals=True,
        strip_comments=False,
        redaction_mode="irreversible",
        redaction_policy="sensitive",
        sensitive_columns={"email", "score"},
    )
    assert "a@b.com" not in result.output_sql
    assert "42" not in result.output_sql
    assert "active" in result.output_sql
