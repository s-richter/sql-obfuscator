import pytest

from sql_obfuscator.errors import WorkspaceError
from sql_obfuscator.workflow import (
    DeobfuscationSafetyError,
    LlmSafetyError,
    ObfuscationOptions,
    analyze_deobfuscation,
    prepare_workspace,
    require_safe_deobfuscation,
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
    assert prepared.snapshot.llm_workflow_report["llm_safe_requested"] is False
    assert prepared.snapshot.llm_workflow_report["llm_safe_approved"] is False


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
