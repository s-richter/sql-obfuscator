from __future__ import annotations

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
