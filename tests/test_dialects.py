from __future__ import annotations

import pytest

from sql_obfuscator.deobfuscation import deobfuscate_sql_with_report
from sql_obfuscator.dialects_factory import get_dialect_profile, supported_dialects
from sql_obfuscator.errors import WorkspaceError
from sql_obfuscator.pipeline import obfuscate_sql_with_metadata


def test_supported_dialects_includes_tsql_and_hive():
    assert "tsql" in supported_dialects()
    assert "hive" in supported_dialects()


def test_get_dialect_profile_unsupported_raises():
    with pytest.raises(WorkspaceError):
        get_dialect_profile("postgres")


def test_tsql_profile_normalizes_temp_table_identifiers():
    profile = get_dialect_profile("tsql")
    normalized = profile.normalize_identifier("[#TempOrders]")
    assert normalized.value == "temporders"
    assert normalized.temp_prefix == "#"
    assert normalized.original_unquoted == "TempOrders"
    assert normalized.original_was_quoted is True


def test_hive_profile_normalizes_backtick_identifiers():
    profile = get_dialect_profile("hive")
    normalized = profile.normalize_identifier("`OrderTotal`")
    assert normalized.value == "ordertotal"
    assert normalized.temp_prefix == ""
    assert normalized.original_unquoted == "OrderTotal"
    assert normalized.original_was_quoted is True


def test_hive_roundtrip_obfuscate_then_deobfuscate():
    sql = "SELECT `order_id`, `order_total` FROM `orders`"
    obfuscation = obfuscate_sql_with_metadata(sql, dialect="hive", seed=7, pretty=True)
    restored_sql, report = deobfuscate_sql_with_report(
        obfuscation.output_sql,
        mapping_payload=obfuscation.mapping_payload,
        context_payload=obfuscation.context_payload,
    )
    assert report["unknown_count"] == 0
    assert report["ambiguous_count"] == 0
    assert "order_id" in restored_sql
    assert "order_total" in restored_sql
    assert "orders" in restored_sql


def test_hive_quoted_identifier_mapping_uses_backtick_normalization():
    sql = "SELECT `case_id`, `alert_family` FROM `risk_cases`"
    obfuscation = obfuscate_sql_with_metadata(sql, dialect="hive", seed=31, pretty=True)

    case_entry = next(
        entry
        for entry in obfuscation.mapping_payload["entries"]
        if entry["normalized_original"] == "case_id"
    )
    alert_entry = next(
        entry
        for entry in obfuscation.mapping_payload["entries"]
        if entry["normalized_original"] == "alert_family"
    )

    assert case_entry["original_unbracketed"] == "case_id"
    assert alert_entry["original_unbracketed"] == "alert_family"
    assert case_entry["original_lexeme"] == "`case_id`"
    assert alert_entry["original_lexeme"] == "`alert_family`"


def test_tsql_merge_output_into_with_schema_qualified_target_roundtrips():
    sql = """
MERGE dbo.CustomerOrderSummary AS target
USING (
    SELECT 1 AS CustomerId
) AS source
    ON target.CustomerId = source.CustomerId
WHEN MATCHED THEN
    UPDATE SET target.OrderCount = 1
OUTPUT
    $action,
    inserted.CustomerId,
    deleted.CustomerId,
    inserted.LastRefreshUtc
INTO dbo.CustomerOrderSummaryAudit
(
    MergeAction,
    InsertedCustomerId,
    DeletedCustomerId,
    MergeUtc
);
""".strip()
    obfuscation = obfuscate_sql_with_metadata(sql, dialect="tsql", seed=7, pretty=True)
    restored_sql, report = deobfuscate_sql_with_report(
        obfuscation.output_sql,
        mapping_payload=obfuscation.mapping_payload,
        context_payload=obfuscation.context_payload,
    )

    assert report["unknown_count"] == 0
    assert report["ambiguous_count"] == 0
    assert "INTO DBO.CUSTOMERORDERSUMMARYAUDIT(" in obfuscation.output_sql
    assert "INTO DBO.CUSTOMERORDERSUMMARYAUDIT(" in restored_sql


def test_tsql_save_transaction_waitfor_and_for_json_roundtrip():
    sql = """
BEGIN TRY
    BEGIN TRANSACTION;
    SAVE TRANSACTION BeforeReconChecks;
    SELECT (
        SELECT t.CustomerId
        FROM dbo.CustomerOrderSummary t
        FOR JSON PATH, INCLUDE_NULL_VALUES
    ) AS SummaryJson;
    COMMIT TRANSACTION;
END TRY
BEGIN CATCH
    IF XACT_STATE() = -1
        ROLLBACK TRANSACTION;
    ELSE IF XACT_STATE() = 1
        ROLLBACK TRANSACTION BeforeReconChecks;
END CATCH;
WAITFOR DELAY '00:00:01';
""".strip()
    obfuscation = obfuscate_sql_with_metadata(sql, dialect="tsql", seed=9, pretty=True)
    restored_sql, report = deobfuscate_sql_with_report(
        obfuscation.output_sql,
        mapping_payload=obfuscation.mapping_payload,
        context_payload=obfuscation.context_payload,
    )

    assert report["unknown_count"] == 0
    assert report["ambiguous_count"] == 0
    assert "SAVE TRANSACTION BeforeReconChecks;" in restored_sql
    assert "FOR JSON PATH, INCLUDE_NULL_VALUES" in restored_sql
    assert "WAITFOR DELAY '00:00:01';" in restored_sql


def test_tsql_projection_alias_preserves_bracketed_case_when_column_name_matches():
    sql = """
SELECT
    re.JournalId AS [journalId]
FROM dbo.ReconExceptions re
FOR XML PATH('exception'), ROOT('exceptions'), TYPE;
""".strip()
    obfuscation = obfuscate_sql_with_metadata(sql, dialect="tsql", seed=11, pretty=True)
    restored_sql, report = deobfuscate_sql_with_report(
        obfuscation.output_sql,
        mapping_payload=obfuscation.mapping_payload,
        context_payload=obfuscation.context_payload,
    )

    assert report["unknown_count"] == 0
    assert report["ambiguous_count"] == 0
    assert "re.JournalId AS [journalId]" in restored_sql


def test_tsql_if_exists_begin_end_with_waitfor_roundtrips():
    sql = """
IF EXISTS
(
    SELECT 1
    FROM #SupplierRiskAlerts
    WHERE SeverityCode = N'CRITICAL'
)
BEGIN
    WAITFOR DELAY '00:00:02';
END;
""".strip()
    obfuscation = obfuscate_sql_with_metadata(sql, dialect="tsql", seed=13, pretty=True)
    restored_sql, report = deobfuscate_sql_with_report(
        obfuscation.output_sql,
        mapping_payload=obfuscation.mapping_payload,
        context_payload=obfuscation.context_payload,
    )

    assert report["unknown_count"] == 0
    assert report["ambiguous_count"] == 0
    assert "IF EXISTS" in restored_sql
    assert "WAITFOR DELAY '00:00:02';" in restored_sql


def test_tsql_set_options_are_not_obfuscated():
    sql = """
SET NOCOUNT ON;
SET XACT_ABORT ON;
SET DEADLOCK_PRIORITY LOW;
""".strip()
    obfuscation = obfuscate_sql_with_metadata(sql, dialect="tsql", seed=17, pretty=True)

    assert "SET NOCOUNT ON;" in obfuscation.output_sql
    assert "SET XACT_ABORT ON;" in obfuscation.output_sql
    assert "SET DEADLOCK_PRIORITY LOW" in obfuscation.output_sql


def test_tsql_open_close_and_deallocate_roundtrip_as_raw_statements():
    sql = """
OPEN AlertDispatchCursor;
CLOSE AlertDispatchCursor;
DEALLOCATE AlertDispatchCursor;
""".strip()
    obfuscation = obfuscate_sql_with_metadata(sql, dialect="tsql", seed=19, pretty=True)
    restored_sql, report = deobfuscate_sql_with_report(
        obfuscation.output_sql,
        mapping_payload=obfuscation.mapping_payload,
        context_payload=obfuscation.context_payload,
    )

    assert report["unknown_count"] == 0
    assert report["ambiguous_count"] == 0
    assert "OPEN AlertDispatchCursor;" in restored_sql
    assert "CLOSE AlertDispatchCursor;" in restored_sql
    assert "DEALLOCATE AlertDispatchCursor;" in restored_sql


def test_tsql_scalar_for_json_subquery_with_option_list_roundtrips():
    sql = """
SELECT
    (
        SELECT
            1 AS [priority],
            N'EUROPE' AS [region]
        FOR JSON PATH, WITHOUT_ARRAY_WRAPPER, INCLUDE_NULL_VALUES
    ) AS AlertPayload;
""".strip()
    obfuscation = obfuscate_sql_with_metadata(sql, dialect="tsql", seed=23, pretty=True)
    restored_sql, report = deobfuscate_sql_with_report(
        obfuscation.output_sql,
        mapping_payload=obfuscation.mapping_payload,
        context_payload=obfuscation.context_payload,
    )

    assert report["unknown_count"] == 0
    assert report["ambiguous_count"] == 0
    assert "FOR JSON PATH, WITHOUT_ARRAY_WRAPPER, INCLUDE_NULL_VALUES" in restored_sql


def test_tsql_scalar_for_json_subquery_with_root_option_roundtrips():
    sql = """
SELECT
    (
        SELECT
            1 AS [priority],
            N'EUROPE' AS [region]
        FOR JSON PATH, ROOT('liquidityAlert'), INCLUDE_NULL_VALUES
    ) AS AlertPayload;
""".strip()
    obfuscation = obfuscate_sql_with_metadata(sql, dialect="tsql", seed=29, pretty=True)
    restored_sql, report = deobfuscate_sql_with_report(
        obfuscation.output_sql,
        mapping_payload=obfuscation.mapping_payload,
        context_payload=obfuscation.context_payload,
    )

    assert report["unknown_count"] == 0
    assert report["ambiguous_count"] == 0
    assert "FOR JSON PATH, ROOT('liquidityAlert'), INCLUDE_NULL_VALUES" in restored_sql
