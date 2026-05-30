from __future__ import annotations

from sql_obfuscator.cli import _summarize_sqlglot_warnings
from sql_obfuscator.workflow import (
    _build_roundtrip_diff_text,
    _normalize_sql_for_comparison,
)
from sql_obfuscator.deobfuscation import deobfuscate_sql_with_report
from sql_obfuscator.pipeline import obfuscate_sql_with_metadata


def test_deobfuscate_roundtrip_recovers_identifiers():
    original_sql = """
    SELECT [UserId] AS TotalAmount, u.UserName
    FROM dbo.Users u
    JOIN Orders o ON u.UserId = o.UserId
    WHERE u.Status = 'Active';
    """
    obfuscated = obfuscate_sql_with_metadata(original_sql, seed=123, pretty=True)
    deobfuscated_sql, report = deobfuscate_sql_with_report(
        obfuscated.output_sql,
        mapping_payload=obfuscated.mapping_payload,
        context_payload=obfuscated.context_payload,
        pretty=True,
    )

    assert "[UserId]" in deobfuscated_sql
    assert "TotalAmount" in deobfuscated_sql
    assert "dbo.Users" in deobfuscated_sql
    assert "Orders" in deobfuscated_sql
    assert "mapped_identifiers" in report
    assert report["unknown_count"] == 0
    assert report["ambiguous_count"] == 0
    assert report["low_confidence_count"] == 0


def test_deobfuscate_reports_unknown_identifiers():
    original_sql = "SELECT UserId FROM Users;"
    obfuscated = obfuscate_sql_with_metadata(original_sql, seed=42, pretty=False)
    edited_obfuscated = f"{obfuscated.output_sql}; SELECT mystery_alias FROM mystery_table"

    deobfuscated_sql, report = deobfuscate_sql_with_report(
        edited_obfuscated,
        mapping_payload=obfuscated.mapping_payload,
        context_payload=obfuscated.context_payload,
        pretty=False,
    )

    assert "mystery_alias" in deobfuscated_sql
    assert "mystery_table" in deobfuscated_sql
    assert report["unknown_count"] > 0
    assert "unknown_by_kind" in report
    assert report["unknown_by_kind"]
    assert "low_confidence_count" in report
    assert "recommendations" in report
    assert len(report["recommendations"]) > 0


def test_deobfuscate_roundtrip_preserves_single_hash_temp_table():
    original_sql = """
    CREATE TABLE #TempOrders (OrderId INT);
    INSERT INTO #TempOrders VALUES (1);
    SELECT * FROM #TempOrders;
    DROP TABLE #TempOrders;
    """
    obfuscated = obfuscate_sql_with_metadata(original_sql, seed=123, pretty=True)
    deobfuscated_sql, report = deobfuscate_sql_with_report(
        obfuscated.output_sql,
        mapping_payload=obfuscated.mapping_payload,
        context_payload=obfuscated.context_payload,
        pretty=True,
    )

    assert "#TempOrders" in deobfuscated_sql
    assert "##TempOrders" not in deobfuscated_sql
    assert report["unknown_count"] == 0
    assert report["ambiguous_count"] == 0

    temp_entry = next(
        entry
        for entry in obfuscated.mapping_payload["entries"]
        if entry["normalized_original"] == "temporders" and entry["temp_prefix"] == "#"
    )
    assert temp_entry["original_unbracketed"] == "TempOrders"


def test_deobfuscate_roundtrip_preserves_global_temp_table_prefix():
    original_sql = """
    CREATE TABLE ##GlobalQueue (Id INT);
    INSERT INTO ##GlobalQueue VALUES (1);
    SELECT * FROM ##GlobalQueue;
    DROP TABLE ##GlobalQueue;
    """
    obfuscated = obfuscate_sql_with_metadata(original_sql, seed=321, pretty=True)
    deobfuscated_sql, report = deobfuscate_sql_with_report(
        obfuscated.output_sql,
        mapping_payload=obfuscated.mapping_payload,
        context_payload=obfuscated.context_payload,
        pretty=True,
    )

    assert "##GlobalQueue" in deobfuscated_sql
    assert "###GlobalQueue" not in deobfuscated_sql
    assert report["unknown_count"] == 0
    assert report["ambiguous_count"] == 0

    temp_entry = next(
        entry
        for entry in obfuscated.mapping_payload["entries"]
        if entry["normalized_original"] == "globalqueue" and entry["temp_prefix"] == "##"
    )
    assert temp_entry["original_unbracketed"] == "GlobalQueue"


def test_deobfuscate_roundtrip_preserves_decimal_type_lexeme():
    original_sql = """
    CREATE TABLE #TempOrders (
      OrderTotal DECIMAL(10, 2)
    );
    """
    obfuscated = obfuscate_sql_with_metadata(original_sql, seed=77, pretty=True)
    deobfuscated_sql, report = deobfuscate_sql_with_report(
        obfuscated.output_sql,
        mapping_payload=obfuscated.mapping_payload,
        context_payload=obfuscated.context_payload,
        pretty=True,
    )

    assert "OrderTotal DECIMAL(10, 2)" in deobfuscated_sql
    assert "OrderTotal NUMERIC(10, 2)" not in deobfuscated_sql
    assert report["unknown_count"] == 0
    assert report["ambiguous_count"] == 0


def test_deobfuscate_roundtrip_preserves_numeric_type_lexeme():
    original_sql = """
    CREATE TABLE #TempOrders (
      OrderTotal NUMERIC(10, 2)
    );
    """
    obfuscated = obfuscate_sql_with_metadata(original_sql, seed=88, pretty=True)
    deobfuscated_sql, report = deobfuscate_sql_with_report(
        obfuscated.output_sql,
        mapping_payload=obfuscated.mapping_payload,
        context_payload=obfuscated.context_payload,
        pretty=True,
    )

    assert "OrderTotal NUMERIC(10, 2)" in deobfuscated_sql
    assert report["unknown_count"] == 0
    assert report["ambiguous_count"] == 0


def test_deobfuscate_statement_shift_matches_original_anchor_without_low_confidence():
    original_sql = "SELECT UserId FROM Users;"
    obfuscated = obfuscate_sql_with_metadata(original_sql, seed=42, pretty=False)
    edited_obfuscated = f"SELECT 1; {obfuscated.output_sql}"

    deobfuscated_sql, report = deobfuscate_sql_with_report(
        edited_obfuscated,
        mapping_payload=obfuscated.mapping_payload,
        context_payload=obfuscated.context_payload,
        pretty=False,
    )

    assert "UserId" in deobfuscated_sql
    assert "Users" in deobfuscated_sql
    assert report["unknown_count"] == 0
    assert report["ambiguous_count"] == 0
    assert report["low_confidence_count"] == 0
    assert report["matched_statement_anchor_count"] == 1
    assert report["unmatched_statement_anchor_count"] == 1
    assert report["statement_anchor_matches"][0]["statement_id"] is None
    assert report["statement_anchor_matches"][1]["statement_id"] == "stmt_0001"


def test_deobfuscate_reports_low_confidence_after_duplicate_statement():
    original_sql = "SELECT UserId FROM Users;"
    obfuscated = obfuscate_sql_with_metadata(original_sql, seed=42, pretty=False)
    edited_obfuscated = f"{obfuscated.output_sql}; {obfuscated.output_sql}"

    deobfuscated_sql, report = deobfuscate_sql_with_report(
        edited_obfuscated,
        mapping_payload=obfuscated.mapping_payload,
        context_payload=obfuscated.context_payload,
        pretty=False,
    )

    assert deobfuscated_sql.count("UserId") >= 2
    assert report["unknown_count"] == 0
    assert report["ambiguous_count"] == 0
    assert report["low_confidence_count"] > 0
    assert report["matched_statement_anchor_count"] == 1
    assert report["unmatched_statement_anchor_count"] == 1



def test_deobfuscate_reports_statement_id_for_unknown_in_matched_statement():
    original_sql = "SELECT UserId FROM Users WHERE UserId > 0;"
    obfuscated = obfuscate_sql_with_metadata(original_sql, seed=42, pretty=False)
    column_entry = next(
        entry
        for entry in obfuscated.mapping_payload["entries"]
        if any(occ.get("kind") == "column" for occ in entry.get("occurrences", []))
    )
    edited_obfuscated = obfuscated.output_sql.replace(column_entry["obfuscated_lexeme"], "mystery_column", 1)

    deobfuscated_sql, report = deobfuscate_sql_with_report(
        edited_obfuscated,
        mapping_payload=obfuscated.mapping_payload,
        context_payload=obfuscated.context_payload,
        pretty=False,
    )

    assert "mystery_column" in deobfuscated_sql
    assert report["unknown_count"] > 0
    assert report["statement_anchor_matches"][0]["statement_id"] == "stmt_0001"
    assert report["unknown_identifiers"][0]["statement_id"] == "stmt_0001"


def test_deobfuscate_roundtrip_restores_projection_alias_matching_column_name():
    original_sql = """
    WITH RankedOrders AS (
        SELECT
            r.UserId AS UserId,
            r.RegionId AS RegionId
        FROM #RecentOrders r
    )
    SELECT
        ro.UserId,
        ro.RegionId
    FROM RankedOrders ro;
    """
    obfuscated = obfuscate_sql_with_metadata(original_sql, seed=123, pretty=True)
    deobfuscated_sql, report = deobfuscate_sql_with_report(
        obfuscated.output_sql,
        mapping_payload=obfuscated.mapping_payload,
        context_payload=obfuscated.context_payload,
        pretty=True,
    )

    assert "AS UserId" in deobfuscated_sql
    assert "AS RegionId" in deobfuscated_sql
    assert report["unknown_count"] == 0
    assert report["ambiguous_count"] == 0
    assert report["low_confidence_count"] == 0


def test_deobfuscate_roundtrip_preserves_tsql_json_access_normalized_shape():
    original_sql = """
    SELECT
        ISNULL(JSON_QUERY(AttributesJson, '$.channel'), JSON_VALUE(AttributesJson, '$.channel')) AS SalesChannel,
        ISNULL(JSON_QUERY(AttributesJson, '$.warehouse'), JSON_VALUE(AttributesJson, '$.warehouse')) AS WarehouseCode,
        TRY_CAST(ISNULL(JSON_QUERY(AttributesJson, '$.priorityScore'), JSON_VALUE(AttributesJson, '$.priorityScore')) AS INT) AS PriorityScore
    FROM #StageOrders;
    """
    obfuscated = obfuscate_sql_with_metadata(original_sql, seed=55, pretty=True)
    deobfuscated_sql, report = deobfuscate_sql_with_report(
        obfuscated.output_sql,
        mapping_payload=obfuscated.mapping_payload,
        context_payload=obfuscated.context_payload,
        pretty=True,
    )

    assert report["unknown_count"] == 0
    assert report["ambiguous_count"] == 0
    assert _normalize_sql_for_comparison(original_sql, dialect="tsql") == _normalize_sql_for_comparison(
        deobfuscated_sql,
        dialect="tsql",
    )


def test_deobfuscate_tsql_set_options_do_not_report_unknown_identifiers():
    original_sql = """
    SET NOCOUNT ON;
    SET XACT_ABORT ON;
    SET DEADLOCK_PRIORITY HIGH;
    """.strip()
    obfuscated = obfuscate_sql_with_metadata(original_sql, seed=66, pretty=True)
    deobfuscated_sql, report = deobfuscate_sql_with_report(
        obfuscated.output_sql,
        mapping_payload=obfuscated.mapping_payload,
        context_payload=obfuscated.context_payload,
        pretty=True,
    )

    assert "SET NOCOUNT ON;" in deobfuscated_sql
    assert "SET XACT_ABORT ON;" in deobfuscated_sql
    assert "SET DEADLOCK_PRIORITY HIGH" in deobfuscated_sql
    assert report["unknown_count"] == 0
    assert report["unknown_by_kind"] == {}


def test_normalized_comparison_ignores_comment_loss():
    original_sql = "-- heading comment\nSELECT 1;"
    deobfuscated_sql = "SELECT 1;"

    assert _normalize_sql_for_comparison(original_sql, dialect="tsql") == _normalize_sql_for_comparison(
        deobfuscated_sql,
        dialect="tsql",
    )


def test_roundtrip_diff_text_suppresses_raw_diff_when_normalized_pair_matches():
    original_sql = "-- heading comment\nSELECT 1;"
    deobfuscated_sql = "SELECT 1;"
    diff_text = _build_roundtrip_diff_text(
        original_sql=original_sql,
        deobfuscated_sql=deobfuscated_sql,
        original_pretty_sql=_normalize_sql_for_comparison(original_sql, dialect="tsql"),
        deobfuscated_pretty_sql=_normalize_sql_for_comparison(deobfuscated_sql, dialect="tsql"),
    )

    assert "No semantic diff detected after normalized comparison." in diff_text
    assert "original.sql" not in diff_text


def test_sqlglot_warning_summary_deduplicates_and_limits_examples():
    summary = _summarize_sqlglot_warnings(
        [
            "'BEGIN TRY' contains unsupported syntax. Falling back to parsing as a 'Command'.",
            "'BEGIN TRY' contains unsupported syntax. Falling back to parsing as a 'Command'.",
            "'EXEC sys.sp_executesql' contains unsupported syntax. Falling back to parsing as a 'Command'.",
            "'END CATCH' contains unsupported syntax. Falling back to parsing as a 'Command'.",
        ]
    )

    assert summary is not None
    assert "4 statement(s)" in summary
    assert "3 unique pattern(s)" in summary
    assert summary.count("Falling back to parsing as a 'Command'.") == 3
