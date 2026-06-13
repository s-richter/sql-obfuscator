import pytest

from sql_obfuscator.errors import WorkspaceError
from sql_obfuscator.workflow import (
    DeobfuscationSafetyError,
    LlmSafetyError,
    ObfuscationOptions,
    TranslationOptions,
    analyze_deobfuscation,
    apply_statement_replacements,
    prepare_workspace,
    require_safe_deobfuscation,
    translate_document,
    validate_deobfuscation,
    verify_roundtrip,
)


def test_prepare_workspace_returns_complete_in_memory_workspace(capsys):
    prepared = prepare_workspace(
        "SELECT UserId FROM Users;",
        input_name="input.sql",
        options=ObfuscationOptions(seed=42),
    )

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""
    assert prepared.original_sql == "SELECT UserId FROM Users;"
    assert prepared.input_name == "input.sql"
    assert "UserId" not in prepared.snapshot.obfuscated_sql
    assert prepared.snapshot.mapping_payload["entries"]
    assert prepared.snapshot.context_payload["statement_count"] == 1
    assert prepared.snapshot.redaction_payload is None
    assert prepared.snapshot.privacy_summary["llm_safe_blocked"] is False
    assert prepared.snapshot.llm_workflow_report["llm_safe_requested"] is False
    assert prepared.safety.approved is True
    assert prepared.safety.blockers == ()
    assert prepared.safety.warnings == ()
    assert "## Statement Anchors" in prepared.instructions_text


def test_prepare_workspace_returns_reversible_redaction_metadata():
    prepared = prepare_workspace(
        "SELECT 'secret' AS Label FROM Users;",
        input_name="input.sql",
        options=ObfuscationOptions(
            redact_literals=True,
            redaction_mode="reversible",
        ),
    )

    assert "__SQL_OBFUSCATOR_STR_" in prepared.snapshot.obfuscated_sql
    assert prepared.snapshot.redaction_payload is not None
    assert prepared.snapshot.redaction_payload["mode"] == "reversible"
    assert prepared.snapshot.redaction_payload["entries"][0]["original_this"] == "secret"
    assert "Preserve placeholder literals exactly" in prepared.instructions_text


def test_prepare_workspace_returns_expert_mode_blockers_and_warnings():
    prepared = prepare_workspace(
        "SELECT @@ROWCOUNT, @UserId, UserId FROM dbo.Users;",
        input_name="input.sql",
    )

    assert prepared.safety.approved is False
    assert any("local variable reference" in item for item in prepared.safety.blockers)
    assert any("system variable" in item for item in prepared.safety.warnings)
    assert any("common schema qualifier" in item for item in prepared.safety.warnings)
    assert {diagnostic.code for diagnostic in prepared.safety.diagnostics} == {
        "privacy.local_variables",
        "privacy.system_variables",
        "privacy.common_schema_qualifiers",
    }
    assert all(diagnostic.recommendation for diagnostic in prepared.safety.diagnostics)
    assert prepared.snapshot.llm_workflow_report["llm_safe_requested"] is False
    assert prepared.snapshot.llm_workflow_report["llm_safe_approved"] is False


def test_prepare_workspace_obfuscates_custom_qualifiers_and_restores_them():
    prepared = prepare_workspace(
        "SELECT sales.Orders.CustomerId FROM CustomerDW.sales.Orders JOIN dbo.Users u ON u.UserId = sales.Orders.UserId;",
        input_name="input.sql",
        options=ObfuscationOptions(seed=42, obfuscate_qualifiers=True),
    )

    obfuscated_sql = prepared.snapshot.obfuscated_sql
    assert "CustomerDW" not in obfuscated_sql
    assert "sales" not in obfuscated_sql
    assert "dbo" in obfuscated_sql
    assert {entry["occurrences"][0]["kind"] for entry in prepared.snapshot.mapping_payload["entries"]} >= {
        "schema_qualifier",
        "catalog_qualifier",
    }
    assert prepared.snapshot.context_payload["obfuscate_qualifiers"] is True
    assert prepared.snapshot.privacy_summary["llm_safe_blocked"] is False
    assert "custom_schema_qualifiers" not in prepared.snapshot.privacy_summary["blocking_identifier_classes"]
    assert "catalog_qualifiers" not in prepared.snapshot.privacy_summary["blocking_identifier_classes"]

    result = analyze_deobfuscation(prepared.snapshot, obfuscated_sql)

    assert "CustomerDW.sales.Orders" in result.deobfuscated_sql
    assert "sales.Orders.CustomerId" in result.deobfuscated_sql
    assert "dbo.Users" in result.deobfuscated_sql
    assert result.safety.has_unresolved is False
    assert result.report["unknown_count"] == 0


def test_prepare_workspace_llm_safe_passes_when_custom_qualifiers_are_obfuscated():
    prepared = prepare_workspace(
        "SELECT UserId FROM sales.Users;",
        input_name="input.sql",
        options=ObfuscationOptions(llm_safe=True, obfuscate_qualifiers=True),
    )

    assert prepared.safety.approved is True
    assert prepared.safety.blockers == ()


def test_prepare_workspace_obfuscates_qualified_function_schema_and_restores_it():
    prepared = prepare_workspace(
        "SELECT sales.NormalizeEmail(CustomerEmail) FROM sales.Customers;",
        input_name="input.sql",
        options=ObfuscationOptions(seed=42, obfuscate_qualifiers=True),
    )

    obfuscated_sql = prepared.snapshot.obfuscated_sql
    assert "sales." not in obfuscated_sql
    assert "NormalizeEmail" in obfuscated_sql
    assert any(
        occurrence["kind"] == "schema_qualifier"
        and occurrence["role"] == "function_schema_qualifier"
        for entry in prepared.snapshot.mapping_payload["entries"]
        for occurrence in entry["occurrences"]
    )

    result = analyze_deobfuscation(prepared.snapshot, obfuscated_sql)

    assert "sales.NormalizeEmail" in result.deobfuscated_sql
    assert result.safety.has_unresolved is False


def test_prepare_workspace_llm_safe_blocks_function_name_after_function_qualifier_obfuscation():
    with pytest.raises(LlmSafetyError) as exc_info:
        prepare_workspace(
            "SELECT sales.NormalizeEmail(CustomerEmail) FROM sales.Customers;",
            input_name="input.sql",
            options=ObfuscationOptions(llm_safe=True, obfuscate_qualifiers=True),
        )

    prepared = exc_info.value.prepared
    assert "sales." not in prepared.snapshot.obfuscated_sql
    assert "NormalizeEmail" in prepared.snapshot.obfuscated_sql
    assert prepared.safety.approved is False
    assert "user_defined_functions" in prepared.snapshot.privacy_summary["blocking_identifier_classes"]
    assert "custom_schema_qualifiers" not in prepared.snapshot.privacy_summary["blocking_identifier_classes"]


def test_prepare_workspace_preserves_common_qualified_function_schema():
    prepared = prepare_workspace(
        "SELECT dbo.NormalizeEmail(CustomerEmail) FROM dbo.Customers;",
        input_name="input.sql",
        options=ObfuscationOptions(obfuscate_qualifiers=True),
    )

    assert "dbo.NormalizeEmail" in prepared.snapshot.obfuscated_sql
    assert "common_schema_qualifiers" in prepared.snapshot.privacy_summary["warning_identifier_classes"]
    assert "custom_schema_qualifiers" not in prepared.snapshot.privacy_summary["blocking_identifier_classes"]


def test_prepare_workspace_obfuscates_hive_qualified_function_schema():
    prepared = prepare_workspace(
        "SELECT sales.normalize_email(customer_email) FROM sales.customers;",
        input_name="input.sql",
        options=ObfuscationOptions(
            dialect="hive",
            seed=42,
            obfuscate_qualifiers=True,
        ),
    )

    assert "sales." not in prepared.snapshot.obfuscated_sql
    assert "normalize_email" in prepared.snapshot.obfuscated_sql.lower()

    result = analyze_deobfuscation(prepared.snapshot, prepared.snapshot.obfuscated_sql)

    assert "sales.normalize_email" in result.deobfuscated_sql.lower()
    assert result.safety.has_unresolved is False


def test_prepare_workspace_returns_structured_sqlglot_warning_diagnostics(capsys):
    prepared = prepare_workspace(
        "BEGIN TRY SELECT UserId FROM Users END TRY BEGIN CATCH SELECT 2 END CATCH;",
        input_name="input.sql",
    )

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""
    sqlglot_diagnostics = [
        diagnostic
        for diagnostic in prepared.diagnostics
        if diagnostic.code == "sqlglot.fallback_parse"
    ]
    assert sqlglot_diagnostics
    assert all(diagnostic.severity == "warning" for diagnostic in sqlglot_diagnostics)
    assert "Falling back to parsing as a 'Command'" in sqlglot_diagnostics[0].message


def test_prepare_workspace_llm_safe_mode_fails_closed_with_prepared_workspace():
    with pytest.raises(LlmSafetyError) as exc_info:
        prepare_workspace(
            "SELECT @UserId, UserId FROM Users;",
            input_name="input.sql",
            options=ObfuscationOptions(llm_safe=True),
        )

    error = exc_info.value
    assert error.prepared.snapshot.llm_workflow_report["llm_safe_requested"] is True
    assert error.prepared.snapshot.llm_workflow_report["llm_safe_approved"] is False
    assert any("local variable reference" in item for item in error.safety.blockers)


def test_prepare_workspace_rejects_redaction_flags_without_redaction_mode():
    with pytest.raises(WorkspaceError, match="Redaction flags require"):
        prepare_workspace(
            "SELECT 'secret';",
            input_name="input.sql",
            options=ObfuscationOptions(redact_literals=True),
        )


def test_apply_statement_replacements_returns_applied_sql_and_report_in_memory(capsys):
    prepared = prepare_workspace(
        "SELECT UserId FROM Users;",
        input_name="input.sql",
    )

    result = apply_statement_replacements(
        prepared.snapshot,
        {
            "schema_version": 1,
            "format": "statement_replacements",
            "edits": [
                {
                    "statement_id": "stmt_0001",
                    "sql": "SELECT 1",
                }
            ],
        },
    )

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""
    assert result.applied_obfuscated_sql == "SELECT 1"
    assert result.report["applied_edit_count"] == 1
    assert result.report["targeted_statement_ids"] == ["stmt_0001"]
    assert result.summary.applied_edit_count == 1
    assert result.summary.untouched_statement_count == 0
    assert result.summary.statement_count == 1
    assert result.summary.targeted_statement_ids == ("stmt_0001",)


def test_apply_statement_replacements_preserves_untouched_statement_exactly():
    prepared = prepare_workspace(
        "SELECT UserId FROM Users; SELECT OrderId FROM Orders;",
        input_name="input.sql",
        options=ObfuscationOptions(pretty=False),
    )
    first_anchor, second_anchor = prepared.snapshot.context_payload["statement_anchors"]

    result = apply_statement_replacements(
        prepared.snapshot,
        {
            "schema_version": 1,
            "format": "statement_replacements",
            "edits": [
                {
                    "statement_id": second_anchor["statement_id"],
                    "sql": f"{second_anchor['obfuscated_sql']} WHERE 1 = 1",
                }
            ],
        },
    )

    replacement_sql = f"{second_anchor['obfuscated_sql']} WHERE 1 = 1"
    assert result.applied_obfuscated_sql == prepared.snapshot.obfuscated_sql.replace(
        second_anchor["obfuscated_sql"],
        replacement_sql,
        1,
    )
    assert first_anchor["obfuscated_sql"] in result.applied_obfuscated_sql
    assert result.report["untouched_statement_count"] == 1
    assert result.summary.untouched_statement_count == 1


def test_apply_statement_replacements_rejects_unknown_statement_id():
    prepared = prepare_workspace(
        "SELECT UserId FROM Users;",
        input_name="input.sql",
    )

    with pytest.raises(WorkspaceError, match="unknown statement_id"):
        apply_statement_replacements(
            prepared.snapshot,
            {
                "schema_version": 1,
                "format": "statement_replacements",
                "edits": [
                    {
                        "statement_id": "stmt_9999",
                        "sql": "SELECT 1",
                    }
                ],
            },
        )


def test_apply_statement_replacements_rejects_malformed_payload():
    prepared = prepare_workspace(
        "SELECT UserId FROM Users;",
        input_name="input.sql",
    )

    with pytest.raises(WorkspaceError, match="'edits' list"):
        apply_statement_replacements(
            prepared.snapshot,
            {
                "schema_version": 1,
                "format": "statement_replacements",
                "edits": "not-a-list",
            },
        )


def test_apply_statement_replacements_rejects_duplicate_statement_id():
    prepared = prepare_workspace(
        "SELECT UserId FROM Users;",
        input_name="input.sql",
    )

    with pytest.raises(WorkspaceError, match="duplicate statement_id"):
        apply_statement_replacements(
            prepared.snapshot,
            {
                "schema_version": 1,
                "format": "statement_replacements",
                "edits": [
                    {
                        "statement_id": "stmt_0001",
                        "sql": "SELECT 1",
                    },
                    {
                        "statement_id": "stmt_0001",
                        "sql": "SELECT 2",
                    },
                ],
            },
        )


def test_apply_statement_replacements_rejects_multiple_sql_statements():
    prepared = prepare_workspace(
        "SELECT UserId FROM Users;",
        input_name="input.sql",
    )

    with pytest.raises(WorkspaceError, match="exactly one"):
        apply_statement_replacements(
            prepared.snapshot,
            {
                "schema_version": 1,
                "format": "statement_replacements",
                "edits": [
                    {
                        "statement_id": "stmt_0001",
                        "sql": "SELECT 1; SELECT 2;",
                    }
                ],
            },
        )


def test_verify_roundtrip_returns_structured_in_memory_result(capsys):
    result = verify_roundtrip(
        "SELECT UserId FROM Users",
        input_name="input.sql",
        options=ObfuscationOptions(pretty=False),
    )

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""
    assert result.deobfuscation.deobfuscated_sql == "SELECT UserId FROM Users"
    assert result.exact_match is True
    assert result.normalized_exact_match is True
    assert result.report["exact_match"] is True
    assert result.report["normalized_exact_match"] is True
    assert result.report["deobfuscation_report"] is result.deobfuscation.report
    assert result.artifacts.diff_text == ""
    assert result.artifacts.normalized_diff_text == ""


def test_verify_roundtrip_summarizes_non_semantic_raw_diff():
    result = verify_roundtrip(
        "SELECT UserId FROM Users;",
        input_name="input.sql",
    )

    assert result.exact_match is False
    assert result.normalized_exact_match is True
    assert "No semantic diff detected after normalized comparison." in result.artifacts.diff_text
    assert result.artifacts.normalized_diff_text == ""


def test_verify_roundtrip_restores_reversible_redaction_literals():
    result = verify_roundtrip(
        "SELECT UserId FROM Users WHERE Status = 'secret' AND Score = 99;",
        input_name="input.sql",
        options=ObfuscationOptions(
            pretty=False,
            redact_literals=True,
            redaction_mode="reversible",
        ),
    )

    assert "secret" in result.deobfuscation.deobfuscated_sql
    assert "99" in result.deobfuscation.deobfuscated_sql
    assert result.deobfuscation.report["redaction"]["unknown_placeholder_count"] == 0
    assert result.deobfuscation.report["redaction"]["missing_placeholder_count"] == 0
    assert result.deobfuscation.safety.has_unresolved is False


def test_analyze_deobfuscation_restores_identifiers_in_memory(capsys):
    prepared = prepare_workspace(
        "SELECT UserId FROM Users;",
        input_name="input.sql",
        options=ObfuscationOptions(seed=42),
    )

    result = analyze_deobfuscation(
        prepared.snapshot,
        prepared.snapshot.obfuscated_sql,
    )

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""
    assert "UserId" in result.deobfuscated_sql
    assert "Users" in result.deobfuscated_sql
    assert result.report["unknown_count"] == 0
    assert result.report["ambiguous_count"] == 0
    assert result.safety.has_unresolved is False
    assert result.safety.has_low_confidence is False
    assert result.summary.unknown_count == 0
    assert result.summary.ambiguous_count == 0
    assert result.summary.mapped_identifiers > 0
    assert result.llm_workflow_report["deobfuscation_summary"]["mapped_identifiers"] > 0


def test_analyze_deobfuscation_restores_reversible_redaction_placeholders():
    prepared = prepare_workspace(
        "SELECT UserId FROM Users WHERE Status = 'secret' AND Score = 99;",
        input_name="input.sql",
        options=ObfuscationOptions(
            redact_literals=True,
            redaction_mode="reversible",
        ),
    )

    result = analyze_deobfuscation(
        prepared.snapshot,
        prepared.snapshot.obfuscated_sql,
    )

    assert "secret" in result.deobfuscated_sql
    assert "99" in result.deobfuscated_sql
    assert result.report["redaction"]["missing_placeholder_count"] == 0
    assert result.safety.has_unresolved is False


def test_analyze_deobfuscation_reports_missing_reversible_redaction_placeholder():
    prepared = prepare_workspace(
        "SELECT UserId FROM Users WHERE Status = 'secret';",
        input_name="input.sql",
        options=ObfuscationOptions(
            redact_literals=True,
            redaction_mode="reversible",
        ),
    )
    edited_sql = prepared.snapshot.obfuscated_sql.replace(
        "__SQL_OBFUSCATOR_STR_",
        "__SQL_OBFUSCATOR_STR_BROKEN_",
        1,
    )

    result = analyze_deobfuscation(prepared.snapshot, edited_sql)

    assert result.safety.has_unresolved is True
    assert result.safety.unknown_identifier_count == 0
    assert result.safety.ambiguous_identifier_count == 0
    assert result.safety.unknown_placeholder_count == 1
    assert result.safety.missing_placeholder_count == 1


def test_analyze_deobfuscation_reports_unknown_identifiers_separately_from_low_confidence():
    prepared = prepare_workspace(
        "SELECT UserId FROM Users;",
        input_name="input.sql",
    )

    result = analyze_deobfuscation(
        prepared.snapshot,
        "SELECT unknown_identifier FROM unknown_table;",
    )

    assert result.safety.has_unresolved is True
    assert result.safety.has_low_confidence is False
    assert result.safety.unknown_identifier_count == 2
    assert result.safety.ambiguous_identifier_count == 0
    assert result.safety.low_confidence_mapping_count == 0
    identifier_diagnostics = [
        diagnostic
        for diagnostic in result.diagnostics
        if diagnostic.code == "deobfuscation.unknown_identifier"
    ]
    assert len(identifier_diagnostics) == 2
    assert {diagnostic.code for diagnostic in identifier_diagnostics} == {
        "deobfuscation.unknown_identifier",
    }
    assert {diagnostic.identifier_kind for diagnostic in identifier_diagnostics} == {
        "column",
        "table",
    }
    assert {diagnostic.statement_anchor for diagnostic in identifier_diagnostics} == {
        None,
    }
    assert {
        diagnostic.code for diagnostic in result.diagnostics
    } == {
        "deobfuscation.unknown_identifier",
        "deobfuscation.unmatched_statement_anchor",
    }


def test_analyze_deobfuscation_returns_structured_redaction_diagnostics():
    prepared = prepare_workspace(
        "SELECT UserId FROM Users WHERE Status = 'secret';",
        input_name="input.sql",
        options=ObfuscationOptions(
            redact_literals=True,
            redaction_mode="reversible",
        ),
    )
    edited_sql = prepared.snapshot.obfuscated_sql.replace(
        "__SQL_OBFUSCATOR_STR_",
        "__SQL_OBFUSCATOR_STR_BROKEN_",
        1,
    )

    result = analyze_deobfuscation(prepared.snapshot, edited_sql)

    assert {diagnostic.code for diagnostic in result.diagnostics} >= {
        "redaction.unknown_placeholder",
        "redaction.missing_placeholder",
    }
    assert all(
        diagnostic.severity == "error"
        for diagnostic in result.diagnostics
        if diagnostic.code.startswith("redaction.")
    )
    assert {
        diagnostic.statement_anchor
        for diagnostic in result.diagnostics
        if diagnostic.code.startswith("redaction.")
    } == {
        None,
    }


def test_analyze_deobfuscation_reports_ambiguous_identifiers_separately_from_other_findings():
    prepared = prepare_workspace(
        "SELECT UserId AS Shared FROM Users;",
        input_name="input.sql",
    )
    alias_entry = next(
        entry
        for entry in prepared.snapshot.mapping_payload["entries"]
        if entry.get("namespace") == "column_alias"
    )

    result = analyze_deobfuscation(
        prepared.snapshot,
        f"SELECT {alias_entry['obfuscated_lexeme']};",
    )

    assert result.safety.has_unresolved is True
    assert result.safety.has_low_confidence is False
    assert result.safety.unknown_identifier_count == 0
    assert result.safety.ambiguous_identifier_count == 1
    assert result.safety.unknown_placeholder_count == 0
    assert result.safety.missing_placeholder_count == 0
    assert result.safety.low_confidence_mapping_count == 0
    assert result.diagnostics[0].code == "deobfuscation.ambiguous_identifier"
    assert result.diagnostics[0].statement_anchor == "stmt_0001"
    with pytest.raises(DeobfuscationSafetyError, match="unresolved mappings"):
        require_safe_deobfuscation(result)
    require_safe_deobfuscation(result, allow_unresolved=True)


def test_require_safe_deobfuscation_blocks_unresolved_mappings_unless_overridden():
    prepared = prepare_workspace(
        "SELECT UserId FROM Users;",
        input_name="input.sql",
    )
    result = analyze_deobfuscation(
        prepared.snapshot,
        "SELECT unknown_identifier FROM unknown_table;",
    )

    with pytest.raises(DeobfuscationSafetyError, match="unresolved mappings") as exc_info:
        require_safe_deobfuscation(result)

    assert exc_info.value.reason == "unresolved"
    assert exc_info.value.result is result
    require_safe_deobfuscation(result, allow_unresolved=True)


def test_require_safe_deobfuscation_blocks_low_confidence_mappings_unless_overridden():
    prepared = prepare_workspace(
        "SELECT UserId FROM Users;",
        input_name="input.sql",
    )
    result = analyze_deobfuscation(
        prepared.snapshot,
        f"{prepared.snapshot.obfuscated_sql}; {prepared.snapshot.obfuscated_sql}",
    )

    assert result.safety.has_unresolved is False
    assert result.safety.has_low_confidence is True
    assert result.safety.low_confidence_mapping_count > 0
    with pytest.raises(DeobfuscationSafetyError, match="low-confidence mappings") as exc_info:
        require_safe_deobfuscation(result)

    assert exc_info.value.reason == "low_confidence"
    assert exc_info.value.result is result
    require_safe_deobfuscation(result, allow_low_confidence=True)


def test_validate_deobfuscation_returns_safe_result():
    prepared = prepare_workspace(
        "SELECT UserId FROM Users;",
        input_name="input.sql",
    )

    result = validate_deobfuscation(
        prepared.snapshot,
        prepared.snapshot.obfuscated_sql,
    )

    assert result.safety.has_unresolved is False
    assert "UserId" in result.deobfuscated_sql
    assert "Users" in result.deobfuscated_sql


def test_validate_deobfuscation_blocks_unsafe_result_unless_overridden():
    prepared = prepare_workspace(
        "SELECT UserId FROM Users;",
        input_name="input.sql",
    )

    with pytest.raises(DeobfuscationSafetyError, match="unresolved mappings"):
        validate_deobfuscation(
            prepared.snapshot,
            "SELECT unknown_identifier FROM unknown_table;",
        )

    result = validate_deobfuscation(
        prepared.snapshot,
        "SELECT unknown_identifier FROM unknown_table;",
        allow_unresolved=True,
    )
    assert result.safety.has_unresolved is True


def test_translate_document_returns_structured_success_result():
    result = translate_document(
        "SELECT [UserId] FROM [Users];",
        options=TranslationOptions(
            source_dialect="tsql",
            target_dialect="hive",
            validate=True,
        ),
    )

    assert result.succeeded is True
    assert result.translation.validated is True
    assert result.translation.failed_statement_count == 0
    assert result.summary.source_dialect == "tsql"
    assert result.summary.target_dialect == "hive"
    assert result.summary.failed_statement_count == 0
    assert "UserId" in result.translation.output_sql


def test_translate_document_returns_structured_failure_result():
    result = translate_document(
        "SELECT ((",
        options=TranslationOptions(
            source_dialect="tsql",
            target_dialect="hive",
        ),
    )

    assert result.succeeded is False
    assert result.translation.failed_statement_count == 1
    assert result.diagnostics[0].severity == "error"
    assert result.diagnostics[0].code == "translation.source_parse_failed"
    assert result.diagnostics[0].batch_index == 1
