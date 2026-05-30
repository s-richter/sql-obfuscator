from __future__ import annotations

import argparse
import logging
import sys
from dataclasses import asdict
from contextlib import contextmanager
from pathlib import Path

from .dialects_factory import supported_dialects
from .errors import InputFileError, ObfuscatorError, ParseScriptError, WorkspaceError
from .llm_edits import load_llm_edits_payload
from .translation import translate_sql_with_report
from .workflow import (
    DeobfuscationResult,
    DeobfuscationSafetyError,
    LlmSafetyDecision,
    LlmSafetyError,
    ObfuscationOptions,
    analyze_deobfuscation,
    apply_statement_replacements,
    prepare_workspace,
    require_safe_deobfuscation,
    verify_roundtrip,
)
from .workspace import (
    default_workspace_path,
    load_context_payload,
    load_mapping_payload,
    load_privacy_summary_report,
    load_workspace_snapshot,
    save_deobfuscation_artifacts,
    save_llm_edit_application_report,
    save_llm_workflow_report_if_present,
    save_roundtrip_reports,
    save_translation_artifacts,
    save_workspace_snapshot,
    validate_workspace_integrity,
)


class _SqlglotWarningCapture(logging.Handler):
    def __init__(self) -> None:
        super().__init__(level=logging.WARNING)
        self.messages: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.messages.append(record.getMessage())


@contextmanager
def _capture_sqlglot_warnings() -> list[str]:
    logger = logging.getLogger("sqlglot")
    handler = _SqlglotWarningCapture()
    previous_handlers = list(logger.handlers)
    previous_level = logger.level
    previous_propagate = logger.propagate
    logger.handlers = [handler]
    logger.setLevel(logging.WARNING)
    logger.propagate = False
    try:
        yield handler.messages
    finally:
        logger.handlers = previous_handlers
        logger.setLevel(previous_level)
        logger.propagate = previous_propagate


def _summarize_sqlglot_warnings(messages: list[str]) -> str | None:
    if not messages:
        return None
    unique_messages: list[str] = []
    for message in messages:
        if message not in unique_messages:
            unique_messages.append(message)
    example_count = min(3, len(unique_messages))
    examples = "; ".join(_single_line_warning(message) for message in unique_messages[:example_count])
    summary = (
        f"Notice: sqlglot used fallback parsing for {len(messages)} statement(s) "
        f"({len(unique_messages)} unique pattern(s))."
    )
    if examples:
        summary += f" Examples: {examples}"
    return summary


def _single_line_warning(message: str, max_length: int = 140) -> str:
    flattened = " ".join(part for part in message.split())
    if len(flattened) <= max_length:
        return flattened
    return flattened[: max_length - 3] + "..."


def _add_common_obfuscation_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--workspace",
        default=None,
        help="Workspace folder for saved artifacts (default: <input_stem>.obf)",
    )
    parser.add_argument(
        "--dialect",
        default="tsql",
        choices=supported_dialects(),
        help="SQL dialect profile",
    )
    parser.add_argument("--seed", type=int, default=None, help="Deterministic random seed")
    parser.add_argument(
        "--pretty",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Pretty-format transformed SQL output (default: enabled)",
    )
    parser.add_argument(
        "--strict-go",
        action="store_true",
        help="Fail when T-SQL GO separators are not standalone lines",
    )
    parser.add_argument(
        "--instruction-template",
        default=None,
        help="Optional path to a markdown template used as llm_instructions.md",
    )
    parser.add_argument(
        "--strip-comments",
        action="store_true",
        help="Remove SQL comments in obfuscated output",
    )
    parser.add_argument(
        "--redact-literals",
        action="store_true",
        help="Redact string/numeric literals in obfuscated output",
    )
    parser.add_argument(
        "--redaction-mode",
        choices=("none", "irreversible", "reversible"),
        default="none",
        help="Redaction mode for obfuscated output (default: none)",
    )
    parser.add_argument(
        "--redaction-policy",
        choices=("all", "strings-only", "sensitive"),
        default="all",
        help="Literal redaction policy (default: all)",
    )
    parser.add_argument(
        "--redaction-sensitive-columns",
        default="",
        help="Comma-separated column names used when --redaction-policy sensitive",
    )
    parser.add_argument(
        "--stdout-only",
        action="store_true",
        help="Print SQL to stdout without writing sibling output files",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Optional directory for obfuscated output files (file input only)",
    )
    parser.add_argument(
        "--llm-safe",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Fail closed when obfuscation preserves fallback/raw statements that are unsafe for external LLM sharing",
    )


def _validate_redaction_args(args: argparse.Namespace) -> None:
    uses_redaction_flags = bool(args.strip_comments or args.redact_literals)
    if args.redaction_mode == "none" and uses_redaction_flags:
        raise WorkspaceError(
            "Redaction flags require --redaction-mode irreversible or --redaction-mode reversible."
        )
    if args.redaction_policy == "sensitive" and not args.redaction_sensitive_columns.strip():
        raise WorkspaceError(
            "Sensitive redaction policy requires --redaction-sensitive-columns."
        )
    if args.redaction_policy != "sensitive" and args.redaction_sensitive_columns.strip():
        raise WorkspaceError(
            "--redaction-sensitive-columns requires --redaction-policy sensitive."
        )


def _parse_sensitive_columns(raw: str) -> set[str]:
    if not raw.strip():
        return set()
    return {part.strip().lower() for part in raw.split(",") if part.strip()}


def _add_deobfuscate_args(
    parser: argparse.ArgumentParser,
    *,
    include_dry_run: bool = True,
) -> None:
    parser.add_argument(
        "--workspace",
        required=True,
        help="Path to workspace folder created during obfuscation",
    )
    parser.add_argument(
        "--input",
        required=True,
        help="Path to edited obfuscated SQL script",
    )
    parser.add_argument(
        "--out",
        default=None,
        help="Optional output path for de-obfuscated SQL",
    )
    if include_dry_run:
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Analyze de-obfuscation and print report summary without writing files",
        )
    parser.add_argument(
        "--allow-unresolved",
        action="store_true",
        help="Allow unknown/ambiguous mappings in non-dry-run mode and still write outputs",
    )
    parser.add_argument(
        "--allow-low-confidence",
        action="store_true",
        help="Allow low-confidence mappings in non-dry-run mode and still write outputs",
    )



def _add_apply_llm_edits_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--workspace",
        required=True,
        help="Path to workspace folder created during obfuscation",
    )
    parser.add_argument(
        "--edits",
        required=True,
        help="Path to JSON statement-replacement edits returned by the LLM",
    )
    parser.add_argument(
        "--out",
        default=None,
        help="Optional output path for the applied obfuscated SQL (default: <workspace>/llm_response_obfuscated.sql)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate and summarize the edit payload without writing files",
    )


def build_command_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sql-obfuscator",
        description="SQL obfuscation workspace commands.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    obfuscate_parser = subparsers.add_parser(
        "obfuscate",
        help="Obfuscate a SQL script and persist workspace artifacts",
    )
    obfuscate_parser.add_argument("sql_file", help="Path to input .sql file, or '-' for stdin")
    _add_common_obfuscation_args(obfuscate_parser)

    deobfuscate_parser = subparsers.add_parser(
        "deobfuscate",
        help="De-obfuscate an edited obfuscated SQL script using workspace artifacts",
    )
    _add_deobfuscate_args(deobfuscate_parser, include_dry_run=True)

    validate_before_write_parser = subparsers.add_parser(
        "validate-before-write",
        help="Validate de-obfuscation safety first, then write output if checks pass",
    )
    _add_deobfuscate_args(validate_before_write_parser, include_dry_run=False)

    apply_llm_edits_parser = subparsers.add_parser(
        "apply-llm-edits",
        help="Apply constrained statement-replacement edits to workspace obfuscated SQL",
    )
    _add_apply_llm_edits_args(apply_llm_edits_parser)

    roundtrip_parser = subparsers.add_parser(
        "roundtrip",
        help="Obfuscate and immediately de-obfuscate for verification",
    )
    roundtrip_parser.add_argument("sql_file", help="Path to input .sql file, or '-' for stdin")
    _add_common_obfuscation_args(roundtrip_parser)
    roundtrip_parser.add_argument(
        "--diff-report",
        action="store_true",
        help="Write unified diff to reports/roundtrip_diff.txt",
    )

    translate_parser = subparsers.add_parser(
        "translate",
        help="Translate SQL between supported dialects",
    )
    translate_parser.add_argument(
        "--input",
        required=True,
        help="Path to input .sql file, or '-' for stdin",
    )
    translate_parser.add_argument(
        "--source-dialect",
        required=True,
        choices=supported_dialects(),
        help="Source parser dialect",
    )
    translate_parser.add_argument(
        "--target-dialect",
        required=True,
        choices=supported_dialects(),
        help="Target output dialect",
    )
    translate_parser.add_argument(
        "--out",
        default=None,
        help="Optional output path for translated SQL",
    )
    translate_parser.add_argument(
        "--pretty",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Pretty-format translated SQL output (default: enabled)",
    )
    translate_parser.add_argument(
        "--validate",
        action="store_true",
        help="Validate translated output by parsing in target dialect",
    )
    translate_parser.add_argument(
        "--workspace",
        default=None,
        help="Optional workspace path for translation report artifacts",
    )
    translate_parser.add_argument(
        "--report-only",
        action="store_true",
        help="Skip writing translated SQL and only emit report/summary",
    )
    translate_parser.add_argument(
        "--stdout-only",
        action="store_true",
        help="Print translated SQL to stdout without writing output SQL files",
    )
    translate_parser.add_argument(
        "--output-dir",
        default=None,
        help="Optional directory for translated SQL output files (file input only)",
    )

    workspace_info_parser = subparsers.add_parser(
        "workspace-info",
        help="Show workspace artifact and report status",
    )
    workspace_info_parser.add_argument(
        "--workspace",
        required=True,
        help="Path to workspace folder",
    )
    return parser


def _read_sql_file(path: Path) -> str:
    if not path.exists():
        raise InputFileError(f"Input file not found: {path}")
    if not path.is_file():
        raise InputFileError(f"Input path is not a file: {path}")
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        raise InputFileError(f"Unable to read input file: {path}") from exc


def _read_sql_source(path_or_stdin: str) -> tuple[str, Path | None]:
    if path_or_stdin == "-":
        try:
            return sys.stdin.read(), None
        except OSError as exc:
            raise InputFileError("Unable to read SQL from stdin.") from exc
    path = Path(path_or_stdin)
    return _read_sql_file(path), path


def _output_path_for_input(path: Path) -> Path:
    if path.suffix:
        return path.with_name(f"{path.stem}_obfuscated{path.suffix}")
    return path.with_name(f"{path.name}_obfuscated")


def _translation_output_path_for_input(path: Path, *, target_dialect: str) -> Path:
    if path.suffix:
        return path.with_name(f"{path.stem}_{target_dialect}{path.suffix}")
    return path.with_name(f"{path.name}_{target_dialect}.sql")


def _resolve_output_path_for_input(
    input_path: Path | None,
    *,
    output_dir: str | None,
    builder,
    context: str,
) -> Path | None:
    if output_dir is None:
        if input_path is None:
            return None
        return builder(input_path)
    if input_path is None:
        raise WorkspaceError(f"{context}: --output-dir requires file input (not stdin).")
    output_dir_path = Path(output_dir)
    if output_dir_path.exists() and not output_dir_path.is_dir():
        raise WorkspaceError(f"{context}: --output-dir is not a directory: {output_dir_path}")
    try:
        output_dir_path.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise WorkspaceError(f"{context}: unable to create --output-dir: {output_dir_path}") from exc
    return output_dir_path / builder(input_path).name


def _write_output_file(path: Path, content: str) -> None:
    try:
        path.write_text(content, encoding="utf-8")
    except OSError as exc:
        raise InputFileError(f"Unable to write output file: {path}") from exc


def _read_optional_template(path: str | None) -> str | None:
    if path is None:
        return None
    template_path = Path(path)
    if not template_path.exists():
        raise InputFileError(f"Instruction template not found: {template_path}")
    if not template_path.is_file():
        raise InputFileError(f"Instruction template path is not a file: {template_path}")
    try:
        return template_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise InputFileError(f"Unable to read instruction template: {template_path}") from exc


def _run_obfuscate_command(args: argparse.Namespace) -> int:
    _validate_redaction_args(args)
    if args.stdout_only and args.output_dir:
        raise WorkspaceError("obfuscate: --stdout-only and --output-dir cannot be used together.")
    sql_text, input_path = _read_sql_source(args.sql_file)
    input_reference = input_path if input_path is not None else Path("stdin.sql")
    try:
        prepared = prepare_workspace(
            sql_text,
            input_name=input_reference.name,
            options=ObfuscationOptions(
                dialect=args.dialect,
                seed=args.seed,
                strict_go=args.strict_go,
                pretty=args.pretty,
                redact_literals=args.redact_literals,
                strip_comments=args.strip_comments,
                redaction_mode=args.redaction_mode,
                redaction_policy=args.redaction_policy,
                sensitive_columns=frozenset(
                    _parse_sensitive_columns(args.redaction_sensitive_columns)
                ),
                llm_safe=bool(args.llm_safe),
            ),
        )
    except LlmSafetyError as exc:
        prepared = exc.prepared
    snapshot = prepared.snapshot
    output_sql = snapshot.obfuscated_sql
    llm_instructions_text = _read_optional_template(args.instruction_template)

    workspace_path = Path(args.workspace) if args.workspace else default_workspace_path(input_reference)
    save_workspace_snapshot(
        workspace_path=workspace_path,
        input_path=input_reference,
        original_sql=sql_text,
        snapshot=snapshot,
        instructions_text=(
            llm_instructions_text
            if llm_instructions_text is not None
            else prepared.instructions_text
        ),
    )
    load_workspace_snapshot(workspace_path)
    _render_llm_safety_decision(
        safety=prepared.safety,
        llm_safe_requested=bool(args.llm_safe),
    )

    output_path = _resolve_output_path_for_input(
        input_path,
        output_dir=args.output_dir,
        builder=_output_path_for_input,
        context="obfuscate",
    )
    if output_path is not None and not args.stdout_only:
        _write_output_file(output_path, output_sql)

    print(output_sql)
    return 0


def _deobfuscate_pipeline(
    *,
    workspace_path: Path,
    input_path: Path,
) -> DeobfuscationResult:
    snapshot = load_workspace_snapshot(workspace_path)
    edited_sql = _read_sql_file(input_path)
    return analyze_deobfuscation(snapshot, edited_sql)


def _summarize_llm_safe_findings(findings: list[str]) -> str:
    if not findings:
        return ""
    if len(findings) == 1:
        return findings[0]
    if len(findings) == 2:
        return f"{findings[0]} {findings[1]}"
    return f"{findings[0]} {findings[1]} ({len(findings) - 2} more finding(s) in reports/privacy_summary.json)."


def _render_llm_safety_decision(
    *,
    safety: LlmSafetyDecision,
    llm_safe_requested: bool,
) -> None:
    findings = [*safety.blockers, *safety.warnings]
    if not findings:
        return
    detail = _summarize_llm_safe_findings(findings)
    if llm_safe_requested and safety.blockers:
        raise WorkspaceError(
            "LLM-safe validation failed: "
            f"{detail} Review reports/privacy_summary.json and reports/llm_workflow_report.json "
            "or rerun without --llm-safe for expert mode."
        )
    print(
        "Warning: "
        f"{detail} Review reports/privacy_summary.json and reports/llm_workflow_report.json "
        "before sharing with an external LLM. Use --llm-safe to fail closed.",
        file=sys.stderr,
    )


def _run_apply_llm_edits_command(args: argparse.Namespace) -> int:
    workspace_path = Path(args.workspace)
    edits_path = Path(args.edits)
    snapshot = load_workspace_snapshot(workspace_path)
    edits_payload = load_llm_edits_payload(edits_path)
    result = apply_statement_replacements(snapshot, edits_payload)
    report = result.report

    print("apply-llm-edits summary:")
    print(f"applied_edit_count: {report.get('applied_edit_count', 0)}")
    print(f"untouched_statement_count: {report.get('untouched_statement_count', 0)}")
    print(f"statement_count: {report.get('statement_count', 0)}")
    print(f"targeted_statement_ids: {report.get('targeted_statement_ids', [])}")

    if args.dry_run:
        return 0

    output_path = Path(args.out) if args.out else workspace_path / "llm_response_obfuscated.sql"
    if output_path == workspace_path / "obfuscated.sql":
        raise WorkspaceError("apply-llm-edits cannot overwrite workspace obfuscated.sql")
    _write_output_file(output_path, result.applied_obfuscated_sql)
    save_llm_edit_application_report(workspace_path=workspace_path, report_payload=report)
    print(result.applied_obfuscated_sql)
    return 0


def _run_deobfuscate_command(args: argparse.Namespace) -> int:
    workspace_path = Path(args.workspace)
    input_path = Path(args.input)
    result = _deobfuscate_pipeline(
        workspace_path=workspace_path,
        input_path=input_path,
    )
    report = result.report
    if args.dry_run:
        print("deobfuscate dry-run summary:")
        print(f"mapped_identifiers: {report.get('mapped_identifiers', 0)}")
        print(f"unknown_count: {report.get('unknown_count', 0)}")
        print(f"ambiguous_count: {report.get('ambiguous_count', 0)}")
        print(f"low_confidence_count: {report.get('low_confidence_count', 0)}")
        print(f"unknown_by_kind: {report.get('unknown_by_kind', {})}")
        print(f"ambiguous_by_kind: {report.get('ambiguous_by_kind', {})}")
        print(f"low_confidence_by_kind: {report.get('low_confidence_by_kind', {})}")
        redaction_report = report.get("redaction")
        if isinstance(redaction_report, dict):
            print(f"redaction_unknown_placeholder_count: {redaction_report.get('unknown_placeholder_count', 0)}")
            print(f"redaction_missing_placeholder_count: {redaction_report.get('missing_placeholder_count', 0)}")
        for recommendation in report.get("recommendations", []):
            print(f"recommendation: {recommendation}")
        if result.safety.has_unresolved:
            return 1
        return 0

    try:
        require_safe_deobfuscation(
            result,
            allow_unresolved=bool(args.allow_unresolved),
            allow_low_confidence=bool(args.allow_low_confidence),
        )
    except DeobfuscationSafetyError as exc:
        if exc.reason == "unresolved":
            raise WorkspaceError(
                "De-obfuscation found unresolved mappings. "
                "Use --dry-run for diagnostics or pass --allow-unresolved to force output."
            ) from exc
        raise WorkspaceError(
            "De-obfuscation found low-confidence mappings. "
            "Use --dry-run for diagnostics or pass --allow-low-confidence to force output."
        ) from exc

    output_path = Path(args.out) if args.out else workspace_path / "deobfuscated.sql"
    _write_output_file(output_path, result.deobfuscated_sql)
    save_deobfuscation_artifacts(
        workspace_path=workspace_path,
        deobfuscated_sql=result.deobfuscated_sql,
        report_payload=report,
    )
    save_llm_workflow_report_if_present(
        workspace_path=workspace_path,
        report_payload=result.llm_workflow_report,
    )
    print(result.deobfuscated_sql)
    return 0


def _run_validate_before_write_command(args: argparse.Namespace) -> int:
    workspace_path = Path(args.workspace)
    input_path = Path(args.input)
    result = _deobfuscate_pipeline(
        workspace_path=workspace_path,
        input_path=input_path,
    )
    report = result.report

    print("validate-before-write summary:")
    print(f"mapped_identifiers: {report.get('mapped_identifiers', 0)}")
    print(f"unknown_count: {report.get('unknown_count', 0)}")
    print(f"ambiguous_count: {report.get('ambiguous_count', 0)}")
    print(f"low_confidence_count: {report.get('low_confidence_count', 0)}")
    redaction_report = report.get("redaction")
    if isinstance(redaction_report, dict):
        print(f"redaction_unknown_placeholder_count: {redaction_report.get('unknown_placeholder_count', 0)}")
        print(f"redaction_missing_placeholder_count: {redaction_report.get('missing_placeholder_count', 0)}")

    try:
        require_safe_deobfuscation(
            result,
            allow_unresolved=bool(args.allow_unresolved),
            allow_low_confidence=bool(args.allow_low_confidence),
        )
    except DeobfuscationSafetyError as exc:
        if exc.reason == "unresolved":
            raise WorkspaceError(
                "Validation failed: unresolved mappings found. "
                "Use --allow-unresolved to force output."
            ) from exc
        raise WorkspaceError(
            "Validation failed: low-confidence mappings found. "
            "Use --allow-low-confidence to force output."
        ) from exc

    output_path = Path(args.out) if args.out else workspace_path / "deobfuscated.sql"
    _write_output_file(output_path, result.deobfuscated_sql)
    save_deobfuscation_artifacts(
        workspace_path=workspace_path,
        deobfuscated_sql=result.deobfuscated_sql,
        report_payload=report,
    )
    save_llm_workflow_report_if_present(
        workspace_path=workspace_path,
        report_payload=result.llm_workflow_report,
    )
    print("validation passed: wrote de-obfuscated output")
    print(result.deobfuscated_sql)
    return 0


def _run_roundtrip_command(args: argparse.Namespace) -> int:
    _validate_redaction_args(args)
    if args.stdout_only and args.output_dir:
        raise WorkspaceError("roundtrip: --stdout-only and --output-dir cannot be used together.")
    original_sql, input_path = _read_sql_source(args.sql_file)
    input_reference = input_path if input_path is not None else Path("stdin.sql")
    try:
        result = verify_roundtrip(
            original_sql,
            input_name=input_reference.name,
            options=ObfuscationOptions(
                dialect=args.dialect,
                seed=args.seed,
                strict_go=args.strict_go,
                pretty=args.pretty,
                redact_literals=args.redact_literals,
                strip_comments=args.strip_comments,
                redaction_mode=args.redaction_mode,
                redaction_policy=args.redaction_policy,
                sensitive_columns=frozenset(
                    _parse_sensitive_columns(args.redaction_sensitive_columns)
                ),
                llm_safe=bool(args.llm_safe),
            ),
        )
        prepared = result.prepared
    except LlmSafetyError as exc:
        prepared = exc.prepared
        result = None
    snapshot = prepared.snapshot
    llm_instructions_text = _read_optional_template(args.instruction_template)

    workspace_path = Path(args.workspace) if args.workspace else default_workspace_path(input_reference)
    save_workspace_snapshot(
        workspace_path=workspace_path,
        input_path=input_reference,
        original_sql=original_sql,
        snapshot=snapshot,
        instructions_text=(
            llm_instructions_text
            if llm_instructions_text is not None
            else prepared.instructions_text
        ),
    )
    load_workspace_snapshot(workspace_path)
    _render_llm_safety_decision(
        safety=prepared.safety,
        llm_safe_requested=bool(args.llm_safe),
    )
    if result is None:
        raise WorkspaceError("Roundtrip verification did not complete.")

    output_path = _resolve_output_path_for_input(
        input_path,
        output_dir=args.output_dir,
        builder=_output_path_for_input,
        context="roundtrip",
    )
    if output_path is not None and not args.stdout_only:
        _write_output_file(output_path, snapshot.obfuscated_sql)

    deobfuscation = result.deobfuscation
    save_deobfuscation_artifacts(
        workspace_path=workspace_path,
        deobfuscated_sql=deobfuscation.deobfuscated_sql,
        report_payload=deobfuscation.report,
    )
    save_llm_workflow_report_if_present(
        workspace_path=workspace_path,
        report_payload=deobfuscation.llm_workflow_report,
    )

    save_roundtrip_reports(
        workspace_path=workspace_path,
        report_payload=result.report,
        diff_text=result.artifacts.diff_text if args.diff_report else None,
        original_pretty_sql=result.artifacts.original_pretty_sql,
        deobfuscated_pretty_sql=result.artifacts.deobfuscated_pretty_sql,
        normalized_diff_text=result.artifacts.normalized_diff_text,
    )

    print(deobfuscation.deobfuscated_sql)
    if deobfuscation.safety.has_unresolved or deobfuscation.safety.has_low_confidence:
        return 1
    return 0


def _run_workspace_info_command(args: argparse.Namespace) -> int:
    workspace_path = Path(args.workspace)
    if not workspace_path.exists() or not workspace_path.is_dir():
        raise WorkspaceError(f"Workspace not found or not a directory: {workspace_path}")

    mapping_path = workspace_path / "mapping.json"
    context_path = workspace_path / "context.json"
    original_path = workspace_path / "original.sql"
    obfuscated_path = workspace_path / "obfuscated.sql"
    instructions_path = workspace_path / "llm_instructions.md"
    deobfuscated_path = workspace_path / "deobfuscated.sql"
    reports_path = workspace_path / "reports"
    deobf_report_path = reports_path / "deobfuscation_report.json"
    roundtrip_report_path = reports_path / "roundtrip_report.json"
    coverage_report_path = reports_path / "coverage_report.txt"
    llm_workflow_report_path = reports_path / "llm_workflow_report.json"
    llm_edit_application_report_path = reports_path / "llm_edit_application_report.json"
    privacy_summary_path = reports_path / "privacy_summary.json"
    roundtrip_diff_path = reports_path / "roundtrip_diff.txt"
    original_pretty_path = reports_path / "original_pretty.sql"
    deobfuscated_pretty_path = reports_path / "deobfuscated_pretty.sql"
    roundtrip_normalized_diff_path = reports_path / "roundtrip_normalized_diff.txt"
    translated_path = workspace_path / "translated.sql"
    translation_report_path = reports_path / "translation_report.json"
    redaction_path = workspace_path / "redaction.json"
    redaction_schema_path = workspace_path / "redaction.schema.json"

    mapping_payload = load_mapping_payload(mapping_path)
    context_payload = load_context_payload(context_path)
    integrity_payload = validate_workspace_integrity(workspace_path)
    privacy_summary = (
        load_privacy_summary_report(privacy_summary_path)
        if privacy_summary_path.exists()
        else None
    )

    lines = [
        f"workspace: {workspace_path}",
        f"dialect: {context_payload.get('dialect')}",
        f"seed: {context_payload.get('seed')}",
        f"pretty: {context_payload.get('pretty')}",
        f"batches: {context_payload.get('batch_count')}",
        f"statements: {context_payload.get('statement_count')}",
        f"statement anchors: {len(context_payload.get('statement_anchors', []))}",
        f"mapping entries: {context_payload.get('mapping_entry_count')}",
        f"mapping forward index size: {len(mapping_payload.get('forward_index', {}))}",
        f"mapping reverse index size: {len(mapping_payload.get('reverse_index', {}))}",
        f"integrity algorithm: {integrity_payload.get('algorithm')}",
        f"integrity tracked files: {len(integrity_payload.get('files', {}))}",
        f"original.sql: {'yes' if original_path.exists() else 'no'}",
        f"obfuscated.sql: {'yes' if obfuscated_path.exists() else 'no'}",
        f"llm_instructions.md: {'yes' if instructions_path.exists() else 'no'}",
        f"deobfuscated.sql: {'yes' if deobfuscated_path.exists() else 'no'}",
        f"reports/deobfuscation_report.json: {'yes' if deobf_report_path.exists() else 'no'}",
        f"reports/roundtrip_report.json: {'yes' if roundtrip_report_path.exists() else 'no'}",
        f"reports/coverage_report.txt: {'yes' if coverage_report_path.exists() else 'no'}",
        f"reports/llm_workflow_report.json: {'yes' if llm_workflow_report_path.exists() else 'no'}",
        f"reports/llm_edit_application_report.json: {'yes' if llm_edit_application_report_path.exists() else 'no'}",
        f"reports/privacy_summary.json: {'yes' if privacy_summary_path.exists() else 'no'}",
        f"privacy llm-safe blocked: {privacy_summary.get('llm_safe_blocked') if isinstance(privacy_summary, dict) else 'n/a'}",
        f"privacy review recommended: {privacy_summary.get('manual_review_recommended') if isinstance(privacy_summary, dict) else 'n/a'}",
        f"reports/roundtrip_diff.txt: {'yes' if roundtrip_diff_path.exists() else 'no'}",
        f"reports/original_pretty.sql: {'yes' if original_pretty_path.exists() else 'no'}",
        f"reports/deobfuscated_pretty.sql: {'yes' if deobfuscated_pretty_path.exists() else 'no'}",
        f"reports/roundtrip_normalized_diff.txt: {'yes' if roundtrip_normalized_diff_path.exists() else 'no'}",
        f"translated.sql: {'yes' if translated_path.exists() else 'no'}",
        f"reports/translation_report.json: {'yes' if translation_report_path.exists() else 'no'}",
        f"redaction.json: {'yes' if redaction_path.exists() else 'no'}",
        f"redaction.schema.json: {'yes' if redaction_schema_path.exists() else 'no'}",
    ]
    print("\n".join(lines))
    return 0


def _run_translate_command(args: argparse.Namespace) -> int:
    sql_text, input_path = _read_sql_source(args.input)
    if args.out and args.stdout_only:
        raise WorkspaceError("translate: --out and --stdout-only cannot be used together.")
    if args.report_only and args.stdout_only:
        raise WorkspaceError("translate: --report-only and --stdout-only cannot be used together.")
    if args.stdout_only and args.output_dir:
        raise WorkspaceError("translate: --stdout-only and --output-dir cannot be used together.")
    if args.out and args.output_dir:
        raise WorkspaceError("translate: --out and --output-dir cannot be used together.")
    result = translate_sql_with_report(
        sql_text,
        source_dialect=args.source_dialect,
        target_dialect=args.target_dialect,
        pretty=args.pretty,
        validate=args.validate,
    )

    print(
        "translate summary: "
        f"source={result.source_dialect} "
        f"target={result.target_dialect} "
        f"statements={result.statement_count} "
        f"failed={result.failed_statement_count} "
        f"warnings={len(result.warnings)}"
    )

    translation_succeeded = result.failed_statement_count == 0 and (not args.validate or result.validated)
    if args.workspace:
        workspace_path = Path(args.workspace)
        save_translation_artifacts(
            workspace_path=workspace_path,
            report_payload=asdict(result),
            translated_sql=(
                result.output_sql
                if translation_succeeded
                and args.out is None
                and not args.report_only
                and not args.stdout_only
                else None
            ),
        )

    if not translation_succeeded:
        return 1
    if args.report_only:
        return 0

    if args.out:
        _write_output_file(Path(args.out), result.output_sql)
        return 0
    if not args.stdout_only:
        output_path = _resolve_output_path_for_input(
            input_path,
            output_dir=args.output_dir,
            builder=lambda p: _translation_output_path_for_input(p, target_dialect=args.target_dialect),
            context="translate",
        )
        if output_path is None:
            print(result.output_sql)
            return 0
        _write_output_file(output_path, result.output_sql)
        return 0
    print(result.output_sql)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_command_parser()
    args = parser.parse_args(argv)

    with _capture_sqlglot_warnings() as sqlglot_warnings:
        try:
            if args.command == "obfuscate":
                rc = _run_obfuscate_command(args)
            elif args.command == "deobfuscate":
                rc = _run_deobfuscate_command(args)
            elif args.command == "roundtrip":
                rc = _run_roundtrip_command(args)
            elif args.command == "validate-before-write":
                rc = _run_validate_before_write_command(args)
            elif args.command == "apply-llm-edits":
                rc = _run_apply_llm_edits_command(args)
            elif args.command == "workspace-info":
                rc = _run_workspace_info_command(args)
            elif args.command == "translate":
                rc = _run_translate_command(args)
            else:
                raise WorkspaceError(f"Unknown command: {args.command}")
        except (ObfuscatorError, ParseScriptError, WorkspaceError) as exc:
            summary = _summarize_sqlglot_warnings(sqlglot_warnings)
            if summary:
                print(summary, file=sys.stderr)
            print(f"Error: {exc}", file=sys.stderr)
            return 1

    summary = _summarize_sqlglot_warnings(sqlglot_warnings)
    if summary:
        print(summary, file=sys.stderr)
    return rc
