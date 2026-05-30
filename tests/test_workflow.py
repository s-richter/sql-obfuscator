import pytest

from sql_obfuscator.errors import WorkspaceError
from sql_obfuscator.workflow import LlmSafetyError, ObfuscationOptions, prepare_workspace


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
