from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .errors import WorkspaceError
from .pipeline import obfuscate_sql_with_metadata
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


class LlmSafetyError(WorkspaceError):
    def __init__(self, prepared: PreparedWorkspace) -> None:
        self.prepared = prepared
        self.safety = prepared.safety
        super().__init__("LLM-safe validation failed.")


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
