from __future__ import annotations

import difflib
from dataclasses import dataclass, field
from typing import Any

from sqlglot.errors import ParseError

from .deobfuscation import deobfuscate_sql_with_report
from .diagnostics import (
    WorkflowDiagnostic,
    deobfuscation_diagnostics,
    privacy_diagnostics,
    translation_diagnostics,
)
from .dialects_factory import get_dialect_profile
from .errors import ParseScriptError, WorkspaceError
from .llm_edits import apply_llm_statement_replacements
from .llm_instructions import build_default_llm_instructions
from .names import IdentifierVocabulary
from .pipeline import obfuscate_sql_with_metadata
from .redaction import restore_reversible_redaction
from .sqlglot_compat import emit_sql, join_emitted_statements, parse_sql
from .translation import TranslationResult, translate_sql_with_report
from .workspace import WorkspaceSnapshot


@dataclass(frozen=True)
class ObfuscationOptions:
    dialect: str = "tsql"
    seed: int | None = None
    strict_go: bool = False
    pretty: bool = True
    redact_literals: bool = False
    strip_comments: bool = False
    redaction_mode: str = "none"
    redaction_policy: str = "all"
    sensitive_columns: frozenset[str] = field(default_factory=frozenset)
    llm_safe: bool = False
    identifier_vocabulary: IdentifierVocabulary | None = None


@dataclass(frozen=True)
class LlmSafetyDecision:
    approved: bool
    blockers: tuple[str, ...]
    warnings: tuple[str, ...]
    diagnostics: tuple[WorkflowDiagnostic, ...] = ()

    @property
    def findings(self) -> tuple[str, ...]:
        if self.diagnostics:
            return tuple(diagnostic.message for diagnostic in self.diagnostics)
        return (*self.blockers, *self.warnings)


@dataclass(frozen=True)
class PreparedWorkspace:
    original_sql: str
    input_name: str
    instructions_text: str
    snapshot: WorkspaceSnapshot
    safety: LlmSafetyDecision


@dataclass(frozen=True)
class StatementReplacementResult:
    applied_obfuscated_sql: str
    report: dict[str, Any]


@dataclass(frozen=True)
class DeobfuscationSafetyDecision:
    has_unresolved: bool
    has_low_confidence: bool
    unknown_identifier_count: int
    ambiguous_identifier_count: int
    unknown_placeholder_count: int
    missing_placeholder_count: int
    low_confidence_mapping_count: int


@dataclass(frozen=True)
class DeobfuscationSummary:
    mapped_identifiers: int
    unknown_count: int
    ambiguous_count: int
    low_confidence_count: int
    unknown_by_kind: dict[str, Any]
    ambiguous_by_kind: dict[str, Any]
    low_confidence_by_kind: dict[str, Any]
    matched_statement_anchor_count: int
    unmatched_statement_anchor_count: int
    redaction_unknown_placeholder_count: int | None
    redaction_missing_placeholder_count: int | None
    recommendations: tuple[str, ...]

    def llm_workflow_payload(self) -> dict[str, Any]:
        return {
            "mapped_identifiers": self.mapped_identifiers,
            "unknown_count": self.unknown_count,
            "ambiguous_count": self.ambiguous_count,
            "low_confidence_count": self.low_confidence_count,
            "matched_statement_anchor_count": self.matched_statement_anchor_count,
            "unmatched_statement_anchor_count": self.unmatched_statement_anchor_count,
            "redaction_unknown_placeholder_count": self.redaction_unknown_placeholder_count or 0,
            "redaction_missing_placeholder_count": self.redaction_missing_placeholder_count or 0,
        }


@dataclass(frozen=True)
class DeobfuscationResult:
    deobfuscated_sql: str
    report: dict[str, Any]
    safety: DeobfuscationSafetyDecision
    summary: DeobfuscationSummary
    llm_workflow_report: dict[str, Any]
    diagnostics: tuple[WorkflowDiagnostic, ...] = ()


@dataclass(frozen=True)
class RoundtripArtifacts:
    diff_text: str
    original_pretty_sql: str
    deobfuscated_pretty_sql: str
    normalized_diff_text: str


@dataclass(frozen=True)
class RoundtripResult:
    prepared: PreparedWorkspace
    deobfuscation: DeobfuscationResult
    exact_match: bool
    normalized_exact_match: bool
    report: dict[str, Any]
    artifacts: RoundtripArtifacts


@dataclass(frozen=True)
class TranslationOptions:
    source_dialect: str
    target_dialect: str
    pretty: bool = True
    validate: bool = False


@dataclass(frozen=True)
class TranslationWorkflowResult:
    translation: TranslationResult
    succeeded: bool
    summary: TranslationSummary
    diagnostics: tuple[WorkflowDiagnostic, ...] = ()


@dataclass(frozen=True)
class TranslationSummary:
    source_dialect: str
    target_dialect: str
    statement_count: int
    failed_statement_count: int
    warning_count: int


class LlmSafetyError(WorkspaceError):
    def __init__(self, prepared: PreparedWorkspace) -> None:
        self.prepared = prepared
        self.safety = prepared.safety
        super().__init__("LLM-safe validation failed.")


class DeobfuscationSafetyError(WorkspaceError):
    def __init__(self, result: DeobfuscationResult, *, reason: str) -> None:
        self.result = result
        self.reason = reason
        if reason == "unresolved":
            message = "De-obfuscation found unresolved mappings."
        else:
            message = "De-obfuscation found low-confidence mappings."
        super().__init__(message)


def prepare_workspace(
    sql: str,
    *,
    input_name: str,
    options: ObfuscationOptions = ObfuscationOptions(),
) -> PreparedWorkspace:
    sensitive_columns = _normalized_sensitive_columns(options.sensitive_columns)
    _validate_obfuscation_options(options, sensitive_columns=sensitive_columns)
    obfuscation = obfuscate_sql_with_metadata(
        sql,
        dialect=options.dialect,
        seed=options.seed,
        strict_go=options.strict_go,
        pretty=options.pretty,
        redact_literals=options.redact_literals,
        strip_comments=options.strip_comments,
        redaction_mode=options.redaction_mode,
        redaction_policy=options.redaction_policy,
        sensitive_columns=sensitive_columns,
        identifier_vocabulary=options.identifier_vocabulary,
    )
    privacy_summary = obfuscation.privacy_summary or {}
    blockers = tuple(
        item for item in privacy_summary.get("blockers", []) if isinstance(item, str)
    )
    warnings = tuple(
        item for item in privacy_summary.get("warnings", []) if isinstance(item, str)
    )
    safety = LlmSafetyDecision(
        approved=not blockers,
        blockers=blockers,
        warnings=warnings,
        diagnostics=privacy_diagnostics(privacy_summary),
    )
    obfuscation_summary = obfuscation.obfuscation_report or {}
    llm_workflow_report = {
        "schema_version": 1,
        "llm_safe_requested": options.llm_safe,
        "llm_safe_approved": bool(obfuscation_summary.get("llm_safe_approved", safety.approved)),
        "obfuscation_summary": obfuscation_summary,
        "deobfuscation_summary": None,
        "recommendations": [
            item
            for item in privacy_summary.get("recommendations", [])
            if isinstance(item, str)
        ],
    }
    instructions_text = build_default_llm_instructions(
        input_name=input_name,
        dialect=options.dialect,
        statement_anchors=obfuscation.context_payload.get("statement_anchors"),
    )
    snapshot = WorkspaceSnapshot(
        obfuscated_sql=obfuscation.output_sql,
        mapping_payload=obfuscation.mapping_payload,
        context_payload=obfuscation.context_payload,
        redaction_payload=obfuscation.redaction_payload,
        privacy_summary=privacy_summary,
        llm_workflow_report=llm_workflow_report,
    )
    prepared = PreparedWorkspace(
        original_sql=sql,
        input_name=input_name,
        instructions_text=instructions_text,
        snapshot=snapshot,
        safety=safety,
    )
    if options.llm_safe and safety.blockers:
        raise LlmSafetyError(prepared)
    return prepared


def apply_statement_replacements(
    snapshot: WorkspaceSnapshot,
    edits_payload: dict[str, Any],
) -> StatementReplacementResult:
    applied_obfuscated_sql, report = apply_llm_statement_replacements(
        obfuscated_sql=snapshot.obfuscated_sql,
        statement_anchors=snapshot.context_payload.get("statement_anchors"),
        batch_count=int(snapshot.context_payload.get("batch_count", 0)),
        dialect=str(snapshot.context_payload.get("dialect", "tsql")),
        edits_payload=edits_payload,
        statement_count=snapshot.context_payload.get("statement_count"),
    )
    return StatementReplacementResult(
        applied_obfuscated_sql=applied_obfuscated_sql,
        report=report,
    )


def analyze_deobfuscation(
    snapshot: WorkspaceSnapshot,
    edited_sql: str,
) -> DeobfuscationResult:
    deobfuscated_sql, report = deobfuscate_sql_with_report(
        edited_sql,
        mapping_payload=snapshot.mapping_payload,
        context_payload=snapshot.context_payload,
    )
    if snapshot.redaction_payload is not None:
        deobfuscated_sql, redaction_report = restore_reversible_redaction(
            deobfuscated_sql,
            dialect=str(snapshot.context_payload.get("dialect", "tsql")),
            pretty=bool(snapshot.context_payload.get("pretty", True)),
            redaction_payload=snapshot.redaction_payload,
        )
        report["redaction"] = redaction_report
    safety = _deobfuscation_safety(report)
    summary = _deobfuscation_summary(report, safety=safety)
    return DeobfuscationResult(
        deobfuscated_sql=deobfuscated_sql,
        report=report,
        safety=safety,
        summary=summary,
        diagnostics=deobfuscation_diagnostics(report),
        llm_workflow_report=_updated_llm_workflow_report(
            snapshot.llm_workflow_report,
            deobfuscation_report=report,
            deobfuscation_summary=summary,
        ),
    )


def require_safe_deobfuscation(
    result: DeobfuscationResult,
    *,
    allow_unresolved: bool = False,
    allow_low_confidence: bool = False,
) -> None:
    if result.safety.has_unresolved and not allow_unresolved:
        raise DeobfuscationSafetyError(result, reason="unresolved")
    if result.safety.has_low_confidence and not allow_low_confidence:
        raise DeobfuscationSafetyError(result, reason="low_confidence")


def validate_deobfuscation(
    snapshot: WorkspaceSnapshot,
    edited_sql: str,
    *,
    allow_unresolved: bool = False,
    allow_low_confidence: bool = False,
) -> DeobfuscationResult:
    result = analyze_deobfuscation(snapshot, edited_sql)
    require_safe_deobfuscation(
        result,
        allow_unresolved=allow_unresolved,
        allow_low_confidence=allow_low_confidence,
    )
    return result


def verify_roundtrip(
    sql: str,
    *,
    input_name: str,
    options: ObfuscationOptions = ObfuscationOptions(),
) -> RoundtripResult:
    prepared = prepare_workspace(
        sql,
        input_name=input_name,
        options=options,
    )
    deobfuscation = analyze_deobfuscation(
        prepared.snapshot,
        prepared.snapshot.obfuscated_sql,
    )
    dialect = str(prepared.snapshot.context_payload.get("dialect", "tsql"))
    try:
        original_pretty_sql = _normalize_sql_for_comparison(sql, dialect=dialect)
        deobfuscated_pretty_sql = _normalize_sql_for_comparison(
            deobfuscation.deobfuscated_sql,
            dialect=dialect,
        )
    except ParseError as exc:
        raise ParseScriptError(
            f"Parse error while building normalized roundtrip comparison: {exc}"
        ) from exc
    normalized_diff_lines = list(
        difflib.unified_diff(
            original_pretty_sql.splitlines(keepends=True),
            deobfuscated_pretty_sql.splitlines(keepends=True),
            fromfile="reports/original_pretty.sql",
            tofile="reports/deobfuscated_pretty.sql",
        )
    )
    diff_text = _build_roundtrip_diff_text(
        original_sql=sql,
        deobfuscated_sql=deobfuscation.deobfuscated_sql,
        original_pretty_sql=original_pretty_sql,
        deobfuscated_pretty_sql=deobfuscated_pretty_sql,
    )
    exact_match = sql == deobfuscation.deobfuscated_sql
    normalized_exact_match = original_pretty_sql == deobfuscated_pretty_sql
    report = {
        "schema_version": 1,
        "exact_match": exact_match,
        "original_char_count": len(sql),
        "deobfuscated_char_count": len(deobfuscation.deobfuscated_sql),
        "diff_line_count": len(diff_text.splitlines()),
        "normalized_exact_match": normalized_exact_match,
        "normalized_original_char_count": len(original_pretty_sql),
        "normalized_deobfuscated_char_count": len(deobfuscated_pretty_sql),
        "normalized_diff_line_count": len(normalized_diff_lines),
        "deobfuscation_report": deobfuscation.report,
    }
    return RoundtripResult(
        prepared=prepared,
        deobfuscation=deobfuscation,
        exact_match=exact_match,
        normalized_exact_match=normalized_exact_match,
        report=report,
        artifacts=RoundtripArtifacts(
            diff_text=diff_text,
            original_pretty_sql=original_pretty_sql,
            deobfuscated_pretty_sql=deobfuscated_pretty_sql,
            normalized_diff_text="".join(normalized_diff_lines),
        ),
    )


def translate_document(
    sql: str,
    *,
    options: TranslationOptions,
) -> TranslationWorkflowResult:
    result = translate_sql_with_report(
        sql,
        source_dialect=options.source_dialect,
        target_dialect=options.target_dialect,
        pretty=options.pretty,
        validate=options.validate,
    )
    return TranslationWorkflowResult(
        translation=result,
        succeeded=(
            result.failed_statement_count == 0
            and (not options.validate or result.validated)
        ),
        summary=TranslationSummary(
            source_dialect=result.source_dialect,
            target_dialect=result.target_dialect,
            statement_count=result.statement_count,
            failed_statement_count=result.failed_statement_count,
            warning_count=len(result.warnings),
        ),
        diagnostics=translation_diagnostics(result),
    )


def _normalize_sql_for_comparison(sql_text: str, *, dialect: str) -> str:
    profile = get_dialect_profile(dialect)
    normalized_batches: list[str] = []
    for batch in profile.split_batches(sql_text):
        if not batch.strip():
            normalized_batches.append(batch)
            continue
        statements = parse_sql(batch, dialect=dialect)
        normalized_batches.append(
            join_emitted_statements(
                [
                    emit_sql(statement, dialect=dialect, pretty=True, strip_comments=True)
                    for statement in statements
                ]
            )
        )
    return profile.join_batches(normalized_batches)


def _build_roundtrip_diff_text(
    *,
    original_sql: str,
    deobfuscated_sql: str,
    original_pretty_sql: str,
    deobfuscated_pretty_sql: str,
) -> str:
    raw_diff = "".join(
        difflib.unified_diff(
            original_sql.splitlines(keepends=True),
            deobfuscated_sql.splitlines(keepends=True),
            fromfile="original.sql",
            tofile="deobfuscated.sql",
        )
    )
    if original_sql == deobfuscated_sql:
        return raw_diff
    if original_pretty_sql == deobfuscated_pretty_sql:
        return (
            "No semantic diff detected after normalized comparison.\n"
            "Raw SQL differs only by non-semantic formatting/comment changes.\n"
            "See reports/original_pretty.sql and reports/deobfuscated_pretty.sql for the normalized pair.\n"
        )
    return raw_diff


def _normalized_sensitive_columns(sensitive_columns: frozenset[str]) -> set[str]:
    return {column.strip().lower() for column in sensitive_columns if column.strip()}


def _validate_obfuscation_options(
    options: ObfuscationOptions,
    *,
    sensitive_columns: set[str],
) -> None:
    uses_redaction_flags = options.strip_comments or options.redact_literals
    if options.redaction_mode == "none" and uses_redaction_flags:
        raise WorkspaceError(
            "Redaction flags require redaction_mode='irreversible' or redaction_mode='reversible'."
        )
    if options.redaction_policy == "sensitive" and not sensitive_columns:
        raise WorkspaceError(
            "Sensitive redaction policy requires --redaction-sensitive-columns "
            "(sensitive_columns in Python)."
        )
    if options.redaction_policy != "sensitive" and sensitive_columns:
        raise WorkspaceError(
            "--redaction-sensitive-columns (sensitive_columns in Python) requires "
            "--redaction-policy sensitive (redaction_policy='sensitive' in Python)."
        )


def _deobfuscation_safety(report: dict[str, Any]) -> DeobfuscationSafetyDecision:
    redaction_report = report.get("redaction")
    unknown_placeholder_count = (
        int(redaction_report.get("unknown_placeholder_count", 0))
        if isinstance(redaction_report, dict)
        else 0
    )
    missing_placeholder_count = (
        int(redaction_report.get("missing_placeholder_count", 0))
        if isinstance(redaction_report, dict)
        else 0
    )
    unknown_identifier_count = int(report.get("unknown_count", 0))
    ambiguous_identifier_count = int(report.get("ambiguous_count", 0))
    low_confidence_mapping_count = int(report.get("low_confidence_count", 0))
    return DeobfuscationSafetyDecision(
        has_unresolved=(
            unknown_identifier_count > 0
            or ambiguous_identifier_count > 0
            or unknown_placeholder_count > 0
            or missing_placeholder_count > 0
        ),
        has_low_confidence=low_confidence_mapping_count > 0,
        unknown_identifier_count=unknown_identifier_count,
        ambiguous_identifier_count=ambiguous_identifier_count,
        unknown_placeholder_count=unknown_placeholder_count,
        missing_placeholder_count=missing_placeholder_count,
        low_confidence_mapping_count=low_confidence_mapping_count,
    )


def _updated_llm_workflow_report(
    current_report: dict[str, Any],
    *,
    deobfuscation_report: dict[str, Any],
    deobfuscation_summary: DeobfuscationSummary,
) -> dict[str, Any]:
    recommendations: list[str] = []
    for recommendation in current_report.get("recommendations", []):
        if isinstance(recommendation, str) and recommendation not in recommendations:
            recommendations.append(recommendation)
    for recommendation in deobfuscation_report.get("recommendations", []):
        if isinstance(recommendation, str) and recommendation not in recommendations:
            recommendations.append(recommendation)
    return {
        **current_report,
        "deobfuscation_summary": deobfuscation_summary.llm_workflow_payload(),
        "recommendations": recommendations,
    }


def _deobfuscation_summary(
    report: dict[str, Any],
    *,
    safety: DeobfuscationSafetyDecision,
) -> DeobfuscationSummary:
    redaction_report = report.get("redaction")
    has_redaction_report = isinstance(redaction_report, dict)
    return DeobfuscationSummary(
        mapped_identifiers=int(report.get("mapped_identifiers", 0)),
        unknown_count=safety.unknown_identifier_count,
        ambiguous_count=safety.ambiguous_identifier_count,
        low_confidence_count=safety.low_confidence_mapping_count,
        unknown_by_kind=_dict_or_empty(report.get("unknown_by_kind")),
        ambiguous_by_kind=_dict_or_empty(report.get("ambiguous_by_kind")),
        low_confidence_by_kind=_dict_or_empty(report.get("low_confidence_by_kind")),
        matched_statement_anchor_count=int(report.get("matched_statement_anchor_count", 0)),
        unmatched_statement_anchor_count=int(report.get("unmatched_statement_anchor_count", 0)),
        redaction_unknown_placeholder_count=(
            safety.unknown_placeholder_count if has_redaction_report else None
        ),
        redaction_missing_placeholder_count=(
            safety.missing_placeholder_count if has_redaction_report else None
        ),
        recommendations=tuple(
            item for item in report.get("recommendations", []) if isinstance(item, str)
        ),
    )


def _dict_or_empty(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}
