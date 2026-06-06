from __future__ import annotations

import logging
import threading
from contextvars import ContextVar
from contextlib import contextmanager
from dataclasses import dataclass
from itertools import zip_longest
from typing import Any, Iterable


@dataclass(frozen=True)
class WorkflowDiagnostic:
    severity: str
    code: str
    message: str
    recommendation: str | None = None
    statement_anchor: str | None = None
    identifier_kind: str | None = None
    batch_index: int | None = None
    statement_index: int | None = None


_sqlglot_warning_buffers: ContextVar[tuple[list[str], ...]] = ContextVar(
    "sqlglot_warning_buffers",
    default=(),
)
_sqlglot_warning_handler: logging.Handler | None = None
_sqlglot_warning_handler_lock = threading.Lock()


class _SqlglotWarningRouter(logging.Handler):
    def __init__(self) -> None:
        super().__init__(level=logging.WARNING)

    def emit(self, record: logging.LogRecord) -> None:
        for messages in _sqlglot_warning_buffers.get():
            messages.append(record.getMessage())


def _ensure_sqlglot_warning_handler(logger: logging.Logger) -> None:
    global _sqlglot_warning_handler
    with _sqlglot_warning_handler_lock:
        if _sqlglot_warning_handler is None:
            _sqlglot_warning_handler = _SqlglotWarningRouter()
        if _sqlglot_warning_handler not in logger.handlers:
            logger.addHandler(_sqlglot_warning_handler)


@contextmanager
def capture_sqlglot_warnings():
    logger = logging.getLogger("sqlglot")
    _ensure_sqlglot_warning_handler(logger)
    messages: list[str] = []
    token = _sqlglot_warning_buffers.set((*_sqlglot_warning_buffers.get(), messages))
    try:
        yield messages
    finally:
        _sqlglot_warning_buffers.reset(token)


def sqlglot_warning_diagnostics(messages: Iterable[str]) -> tuple[WorkflowDiagnostic, ...]:
    return tuple(
        WorkflowDiagnostic(
            severity="warning",
            code="sqlglot.fallback_parse",
            message=message,
            recommendation="Review parser fallback output before relying on transformed SQL.",
        )
        for message in messages
        if message
    )


def summarize_sqlglot_warnings(messages: Iterable[str]) -> str | None:
    warning_messages = list(messages)
    if not warning_messages:
        return None
    unique_messages: list[str] = []
    for message in warning_messages:
        if message not in unique_messages:
            unique_messages.append(message)
    example_count = min(3, len(unique_messages))
    examples = "; ".join(_single_line_warning(message) for message in unique_messages[:example_count])
    summary = (
        f"Notice: sqlglot used fallback parsing for {len(warning_messages)} statement(s) "
        f"({len(unique_messages)} unique pattern(s))."
    )
    if examples:
        summary += f" Examples: {examples}"
    return summary


def summarize_sqlglot_diagnostics(diagnostics: Iterable[WorkflowDiagnostic]) -> str | None:
    return summarize_sqlglot_warnings(
        diagnostic.message
        for diagnostic in diagnostics
        if diagnostic.code == "sqlglot.fallback_parse"
    )


def privacy_diagnostics(summary: dict[str, Any]) -> tuple[WorkflowDiagnostic, ...]:
    diagnostics: list[WorkflowDiagnostic] = []
    diagnostics.extend(
        _privacy_findings(
            summary.get("blockers"),
            identifier_classes=summary.get("blocking_identifier_classes"),
            severity="error",
        )
    )
    diagnostics.extend(
        _privacy_findings(
            summary.get("warnings"),
            identifier_classes=summary.get("warning_identifier_classes"),
            severity="warning",
        )
    )
    return tuple(diagnostics)


def deobfuscation_diagnostics(report: dict[str, Any]) -> tuple[WorkflowDiagnostic, ...]:
    diagnostics: list[WorkflowDiagnostic] = []
    diagnostics.extend(
        _identifier_diagnostics(
            report.get("unknown_identifiers"),
            severity="error",
            code="deobfuscation.unknown_identifier",
            message_template="Unknown obfuscated identifier '{value}' could not be restored.",
            recommendation="Ensure the edit did not introduce or rename obfuscated identifiers.",
        )
    )
    diagnostics.extend(
        _identifier_diagnostics(
            report.get("ambiguous_identifiers"),
            severity="error",
            code="deobfuscation.ambiguous_identifier",
            message_template="Ambiguous obfuscated identifier '{value}' could not be restored safely.",
            recommendation="Keep alias and table structure closer to the obfuscated input.",
        )
    )
    diagnostics.extend(
        _identifier_diagnostics(
            report.get("low_confidence_mappings"),
            severity="warning",
            code="deobfuscation.low_confidence_mapping",
            message_template="Obfuscated identifier '{value}' was restored with low confidence.",
            recommendation="Review the restored SQL or rerun with stricter rewrite constraints.",
        )
    )
    diagnostics.extend(_statement_anchor_diagnostics(report.get("statement_anchor_matches")))
    redaction_report = report.get("redaction")
    if isinstance(redaction_report, dict):
        diagnostics.extend(_redaction_diagnostics(redaction_report))
    return tuple(diagnostics)


def translation_diagnostics(result: Any) -> tuple[WorkflowDiagnostic, ...]:
    diagnostics: list[WorkflowDiagnostic] = []
    warnings = result.warnings if isinstance(result.warnings, list) else []
    for warning in warnings:
        if isinstance(warning, str):
            diagnostics.append(
                WorkflowDiagnostic(
                    severity="warning",
                    code="translation.identifier_shape_change",
                    message=warning,
                    recommendation="Review translated identifier quoting and casing.",
                )
            )
    failures = result.failures if isinstance(result.failures, list) else []
    for failure in failures:
        if not isinstance(failure, dict):
            continue
        stage = failure.get("stage")
        stage_code = stage if isinstance(stage, str) and stage else "unknown"
        error = failure.get("error")
        message = str(error) if error is not None else "Unknown translation failure."
        diagnostics.append(
            WorkflowDiagnostic(
                severity="error",
                code=f"translation.{stage_code}_failed",
                message=message,
                recommendation="Review the source statement and selected dialects.",
                batch_index=_optional_int(failure.get("batch_index")),
                statement_index=_optional_int(failure.get("statement_index")),
            )
        )
    return tuple(diagnostics)


def _privacy_findings(
    messages: Any,
    *,
    identifier_classes: Any,
    severity: str,
) -> list[WorkflowDiagnostic]:
    if not isinstance(messages, list):
        return []
    classes = identifier_classes if isinstance(identifier_classes, list) else []
    diagnostics: list[WorkflowDiagnostic] = []
    for message, identifier_class in zip_longest(messages, classes):
        if not isinstance(message, str):
            continue
        kind = identifier_class if isinstance(identifier_class, str) else None
        diagnostics.append(
            WorkflowDiagnostic(
                severity=severity,
                code=f"privacy.{kind or 'manual_review'}",
                message=message,
                recommendation="Review reports/privacy_summary.json before external sharing.",
                identifier_kind=kind,
            )
        )
    return diagnostics


def _identifier_diagnostics(
    items: Any,
    *,
    severity: str,
    code: str,
    message_template: str,
    recommendation: str,
) -> list[WorkflowDiagnostic]:
    if not isinstance(items, list):
        return []
    diagnostics: list[WorkflowDiagnostic] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        value = item.get("obfuscated")
        diagnostics.append(
            WorkflowDiagnostic(
                severity=severity,
                code=code,
                message=message_template.format(value=value if isinstance(value, str) else "?"),
                recommendation=recommendation,
                statement_anchor=_optional_str(item.get("statement_id")),
                identifier_kind=_optional_str(item.get("kind")),
                batch_index=_optional_int(item.get("batch_index")),
                statement_index=_optional_int(item.get("statement_index")),
            )
        )
    return diagnostics


def _statement_anchor_diagnostics(items: Any) -> list[WorkflowDiagnostic]:
    if not isinstance(items, list):
        return []
    diagnostics: list[WorkflowDiagnostic] = []
    for item in items:
        if not isinstance(item, dict) or isinstance(item.get("statement_id"), str):
            continue
        diagnostics.append(
            WorkflowDiagnostic(
                severity="warning",
                code="deobfuscation.unmatched_statement_anchor",
                message="Edited statement could not be matched to an original statement anchor.",
                recommendation="Review large rewrites, duplicated statements, and reordered blocks.",
                batch_index=_optional_int(item.get("current_batch_index")),
                statement_index=_optional_int(item.get("current_statement_index")),
            )
        )
    return diagnostics


def _redaction_diagnostics(report: dict[str, Any]) -> list[WorkflowDiagnostic]:
    diagnostics: list[WorkflowDiagnostic] = []
    unknown_placeholders = report.get("unknown_placeholders")
    if isinstance(unknown_placeholders, list):
        for placeholder in unknown_placeholders:
            if isinstance(placeholder, str):
                diagnostics.append(
                    WorkflowDiagnostic(
                        severity="error",
                        code="redaction.unknown_placeholder",
                        message=f"Unknown reversible-redaction placeholder '{placeholder}' was found.",
                        recommendation="Preserve generated redaction placeholders exactly during edits.",
                    )
                )
    missing_placeholders = report.get("missing_placeholders")
    if isinstance(missing_placeholders, list):
        for placeholder in missing_placeholders:
            if isinstance(placeholder, str):
                diagnostics.append(
                    WorkflowDiagnostic(
                        severity="error",
                        code="redaction.missing_placeholder",
                        message=f"Expected reversible-redaction placeholder '{placeholder}' is missing.",
                        recommendation="Restore the missing generated placeholder before de-obfuscation.",
                    )
                )
    return diagnostics


def _optional_str(value: Any) -> str | None:
    return value if isinstance(value, str) else None


def _optional_int(value: Any) -> int | None:
    return value if isinstance(value, int) else None


def _single_line_warning(message: str, max_length: int = 140) -> str:
    flattened = " ".join(part for part in message.split())
    if len(flattened) <= max_length:
        return flattened
    return flattened[: max_length - 3] + "..."
