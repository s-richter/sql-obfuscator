from __future__ import annotations

from dataclasses import dataclass

from .errors import InputFileError, ObfuscatorError, ParseScriptError, WorkspaceError
from .workflow import DeobfuscationSafetyError, LlmSafetyError


@dataclass(frozen=True)
class ApplicationErrorPresentation:
    code: str
    title: str
    message: str
    recommendation: str
    severity: str = "error"
    report_paths: tuple[str, ...] = ()


def present_application_error(error: Exception) -> ApplicationErrorPresentation:
    if isinstance(error, LlmSafetyError):
        return ApplicationErrorPresentation(
            code="llm_safety.validation_failed",
            title="External sharing validation failed",
            message=str(error),
            recommendation=(
                "Review the privacy and LLM workflow reports before sharing the SQL externally."
            ),
            report_paths=(
                "reports/privacy_summary.json",
                "reports/llm_workflow_report.json",
            ),
        )
    if isinstance(error, DeobfuscationSafetyError):
        if error.reason == "unresolved":
            return ApplicationErrorPresentation(
                code="deobfuscation.unresolved_mappings",
                title="De-obfuscation needs review",
                message=str(error),
                recommendation=(
                    "Review unresolved identifiers and placeholders before writing restored SQL."
                ),
            )
        return ApplicationErrorPresentation(
            code="deobfuscation.low_confidence_mappings",
            title="De-obfuscation needs review",
            message=str(error),
            recommendation=(
                "Review low-confidence mappings before writing restored SQL."
            ),
        )
    if isinstance(error, InputFileError):
        return ApplicationErrorPresentation(
            code="input_file.error",
            title="Input file error",
            message=str(error),
            recommendation="Check the file path and access permissions, then retry the operation.",
        )
    if isinstance(error, ParseScriptError):
        return ApplicationErrorPresentation(
            code="sql.parse_failed",
            title="SQL parsing failed",
            message=str(error),
            recommendation="Review the reported SQL batch and correct the syntax before retrying.",
        )
    if isinstance(error, WorkspaceError):
        return ApplicationErrorPresentation(
            code="workspace.error",
            title="Workspace error",
            message=str(error),
            recommendation=(
                "Review the workspace path, command options, and integrity state before retrying."
            ),
        )
    if isinstance(error, ObfuscatorError):
        return ApplicationErrorPresentation(
            code="application.error",
            title="Application error",
            message=str(error),
            recommendation="Review the operation inputs and retry.",
        )
    return ApplicationErrorPresentation(
        code="application.unexpected_error",
        title="Unexpected application error",
        message="The operation failed unexpectedly.",
        recommendation="Retry the operation. If it fails again, inspect the application logs.",
    )
