from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .deobfuscation import deobfuscate_sql_with_report
from .errors import WorkspaceError
from .pipeline import obfuscate_sql_with_metadata
from .redaction import restore_reversible_redaction
from .workspace import build_default_llm_instructions


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


@dataclass(frozen=True)
class WorkspaceSnapshot:
    obfuscated_sql: str
    mapping_payload: dict[str, Any]
    context_payload: dict[str, Any]
    redaction_payload: dict[str, Any] | None
    privacy_summary: dict[str, Any]
    llm_workflow_report: dict[str, Any]


@dataclass(frozen=True)
class LlmSafetyDecision:
    approved: bool
    blockers: tuple[str, ...]
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class PreparedWorkspace:
    original_sql: str
    input_name: str
    instructions_text: str
    snapshot: WorkspaceSnapshot
    safety: LlmSafetyDecision


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
class DeobfuscationResult:
    deobfuscated_sql: str
    report: dict[str, Any]
    safety: DeobfuscationSafetyDecision
    llm_workflow_report: dict[str, Any]


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
    return DeobfuscationResult(
        deobfuscated_sql=deobfuscated_sql,
        report=report,
        safety=safety,
        llm_workflow_report=_updated_llm_workflow_report(
            snapshot.llm_workflow_report,
            deobfuscation_report=report,
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
        raise WorkspaceError("Sensitive redaction policy requires sensitive_columns.")
    if options.redaction_policy != "sensitive" and sensitive_columns:
        raise WorkspaceError("sensitive_columns requires redaction_policy='sensitive'.")


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
        "deobfuscation_summary": _deobfuscation_summary(deobfuscation_report),
        "recommendations": recommendations,
    }


def _deobfuscation_summary(report: dict[str, Any]) -> dict[str, Any]:
    safety = _deobfuscation_safety(report)
    return {
        "mapped_identifiers": report.get("mapped_identifiers", 0),
        "unknown_count": safety.unknown_identifier_count,
        "ambiguous_count": safety.ambiguous_identifier_count,
        "low_confidence_count": safety.low_confidence_mapping_count,
        "matched_statement_anchor_count": report.get("matched_statement_anchor_count", 0),
        "unmatched_statement_anchor_count": report.get("unmatched_statement_anchor_count", 0),
        "redaction_unknown_placeholder_count": safety.unknown_placeholder_count,
        "redaction_missing_placeholder_count": safety.missing_placeholder_count,
    }
