from pathlib import Path

import pytest

from sql_obfuscator import cli
from sql_obfuscator.application_errors import (
    ApplicationErrorPresentation,
    present_application_error,
)
from sql_obfuscator.errors import InputFileError, ObfuscatorError, ParseScriptError, WorkspaceError
from sql_obfuscator.workflow import (
    DeobfuscationSafetyError,
    LlmSafetyError,
    ObfuscationOptions,
    analyze_deobfuscation,
    prepare_workspace,
    require_safe_deobfuscation,
)


@pytest.mark.parametrize(
    "error, expected_code, expected_title",
    [
        (InputFileError("Unable to read input.sql"), "input_file.error", "Input file error"),
        (ParseScriptError("Parse error in batch 1/1"), "sql.parse_failed", "SQL parsing failed"),
        (WorkspaceError("Workspace not found"), "workspace.error", "Workspace error"),
        (ObfuscatorError("Operation failed"), "application.error", "Application error"),
    ],
)
def test_present_application_error_maps_known_errors(
    error: Exception,
    expected_code: str,
    expected_title: str,
):
    presentation = present_application_error(error)

    assert presentation.code == expected_code
    assert presentation.title == expected_title
    assert presentation.message == str(error)
    assert presentation.severity == "error"
    assert presentation.recommendation


def test_present_application_error_includes_llm_safety_reports():
    with pytest.raises(LlmSafetyError) as exc_info:
        prepare_workspace(
            "SELECT @UserId, UserId FROM Users;",
            input_name="input.sql",
            options=ObfuscationOptions(llm_safe=True),
        )

    presentation = present_application_error(exc_info.value)

    assert presentation.code == "llm_safety.validation_failed"
    assert presentation.report_paths == (
        "reports/privacy_summary.json",
        "reports/llm_workflow_report.json",
    )


def test_present_application_error_maps_deobfuscation_safety_error():
    prepared = prepare_workspace(
        "SELECT UserId FROM Users;",
        input_name="input.sql",
    )
    result = analyze_deobfuscation(
        prepared.snapshot,
        "SELECT mystery_column FROM mystery_table;",
    )
    with pytest.raises(DeobfuscationSafetyError) as exc_info:
        require_safe_deobfuscation(result)

    presentation = present_application_error(exc_info.value)

    assert presentation.code == "deobfuscation.unresolved_mappings"
    assert "unresolved" in presentation.message
    assert "before writing restored SQL" in presentation.recommendation


def test_present_application_error_hides_unexpected_exception_details():
    presentation = present_application_error(
        RuntimeError("database password exposed from C:\\internal\\secrets.txt")
    )

    assert presentation.code == "application.unexpected_error"
    assert presentation.message == "The operation failed unexpectedly."
    assert "password" not in presentation.message
    assert "C:\\internal" not in presentation.message


def test_cli_renders_shared_application_error_presentation(
    tmp_path: Path,
    monkeypatch,
    capsys,
):
    monkeypatch.setattr(
        cli,
        "present_application_error",
        lambda error: ApplicationErrorPresentation(
            code="test.error",
            title="Test error",
            message="Rendered through shared presenter.",
            recommendation="Retry.",
        ),
    )

    rc = cli.main(["obfuscate", str(tmp_path / "missing.sql")])
    captured = capsys.readouterr()

    assert rc == 1
    assert captured.err == "Error: Rendered through shared presenter.\n"
