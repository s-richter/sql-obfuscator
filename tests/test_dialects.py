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
