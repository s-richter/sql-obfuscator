from __future__ import annotations

from sql_obfuscator.pipeline import obfuscate_sql_with_metadata



def test_privacy_summary_blocks_local_variables_user_defined_functions_and_custom_schemas():
    result = obfuscate_sql_with_metadata(
        "SELECT @UserId, sales.MyFunc(UserId) FROM sales.Users;",
        dialect="tsql",
        seed=7,
    )

    summary = result.privacy_summary or {}
    surface = summary.get("identifier_surface", {})

    assert summary.get("llm_safe_blocked") is True
    assert "local_variables" in summary.get("blocking_identifier_classes", [])
    assert "user_defined_functions" in summary.get("blocking_identifier_classes", [])
    assert "custom_schema_qualifiers" in summary.get("blocking_identifier_classes", [])
    assert surface.get("local_variables", {}).get("occurrence_count") == 1
    assert surface.get("user_defined_functions", {}).get("occurrence_count") == 1
    assert surface.get("custom_schema_qualifiers", {}).get("occurrence_count", 0) >= 1
    assert "@UserId" in surface.get("local_variables", {}).get("examples", [])
    assert "sales.MyFunc" in surface.get("user_defined_functions", {}).get("examples", [])
    assert "sales" in surface.get("custom_schema_qualifiers", {}).get("examples", [])



def test_privacy_summary_warns_for_common_schema_and_system_variables_only():
    result = obfuscate_sql_with_metadata(
        "SELECT @@ROWCOUNT, ABS(UserId) FROM dbo.Users;",
        dialect="tsql",
        seed=7,
    )

    summary = result.privacy_summary or {}
    surface = summary.get("identifier_surface", {})

    assert summary.get("llm_safe_blocked") is False
    assert summary.get("manual_review_recommended") is True
    assert "system_variables" in summary.get("warning_identifier_classes", [])
    assert "common_schema_qualifiers" in summary.get("warning_identifier_classes", [])
    assert surface.get("system_variables", {}).get("occurrence_count") == 1
    assert surface.get("common_schema_qualifiers", {}).get("occurrence_count", 0) >= 1
    assert surface.get("user_defined_functions", {}).get("occurrence_count") == 0
    assert "@@ROWCOUNT" in surface.get("system_variables", {}).get("examples", [])
    assert "dbo" in surface.get("common_schema_qualifiers", {}).get("examples", [])
