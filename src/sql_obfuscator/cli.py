from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .application_errors import present_application_error
from .diagnostics import WorkflowDiagnostic, summarize_sqlglot_diagnostics
from .dialects_factory import supported_dialects
from .errors import InputFileError, ObfuscatorError, ParseScriptError, WorkspaceError
from .llm_edits import load_llm_edits_payload
from .local_application import LocalWorkspaceApplication
from .local_workspace_store import WorkspaceInspection
from .workflow import (
    DeobfuscationSafetyError,
    DeobfuscationSummary,
    LlmSafetyDecision,
    ObfuscationOptions,
    TranslationOptions,
)


def _summarize_sqlglot_warnings(messages: list[str]) -> str | None:
    from .diagnostics import summarize_sqlglot_warnings

    return summarize_sqlglot_warnings(messages)


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
        "--obfuscate-qualifiers",
        action="store_true",
        help="Obfuscate custom schema and catalog/database qualifiers on supported references",
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


def _add_prepare_for_llm_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("sql_file", help="Path to input .sql file, or '-' for stdin")
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
        "--instruction-template",
        default=None,
        help="Optional path to a markdown template used as llm_instructions.md",
    )
    parser.add_argument(
        "--irreversible",
        action="store_true",
        help="Use irreversible literal redaction instead of reversible redaction",
    )
    parser.add_argument(
        "--expert-mode",
        action="store_true",
        help="Allow output that requires manual review instead of failing closed",
    )
    parser.add_argument(
        "--print-sql",
        action="store_true",
        help="Print obfuscated SQL after the workflow summary",
    )


def _add_restore_from_llm_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--workspace",
        required=True,
        help="Path to workspace folder created during preparation",
    )
    parser.add_argument(
        "--edits",
        required=True,
        help="Path to JSON statement-replacement edits returned by the LLM",
    )
    parser.add_argument(
        "--out",
        default=None,
        help="Optional output path for restored SQL (default: <workspace>/deobfuscated.sql)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate edits and restoration safety without writing workflow outputs",
    )
    parser.add_argument(
        "--allow-unresolved",
        action="store_true",
        help="Allow unknown/ambiguous mappings and still write restored output",
    )
    parser.add_argument(
        "--allow-low-confidence",
        action="store_true",
        help="Allow low-confidence mappings and still write restored output",
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

    prepare_for_llm_parser = subparsers.add_parser(
        "prepare-for-llm",
        help="Create LLM-sharing artifacts with recommended workflow defaults",
    )
    _add_prepare_for_llm_args(prepare_for_llm_parser)

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

    restore_from_llm_parser = subparsers.add_parser(
        "restore-from-llm",
        help="Apply bounded LLM edits, validate, and restore SQL",
    )
    _add_restore_from_llm_args(restore_from_llm_parser)

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
    if args.stdout_only and args.output_dir:
        raise WorkspaceError("obfuscate: --stdout-only and --output-dir cannot be used together.")
    sql_text, input_path = _read_sql_source(args.sql_file)
    input_reference = input_path if input_path is not None else Path("stdin.sql")
    application = LocalWorkspaceApplication()
    operation = application.prepare_and_save_workspace(
        sql_text,
        input_path=input_reference,
        workspace_path=Path(args.workspace) if args.workspace else None,
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
            obfuscate_qualifiers=bool(args.obfuscate_qualifiers),
        ),
        instructions_text=_read_optional_template(args.instruction_template),
    )
    prepared = operation.prepared
    snapshot = prepared.snapshot
    output_sql = snapshot.obfuscated_sql
    _render_sqlglot_diagnostics(operation.diagnostics)
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


def _run_prepare_for_llm_command(args: argparse.Namespace) -> int:
    sql_text, input_path = _read_sql_source(args.sql_file)
    input_reference = input_path if input_path is not None else Path("stdin.sql")
    redaction_mode = "irreversible" if args.irreversible else "reversible"
    operation = LocalWorkspaceApplication().prepare_and_save_workspace(
        sql_text,
        input_path=input_reference,
        workspace_path=Path(args.workspace) if args.workspace else None,
        options=ObfuscationOptions(
            dialect=args.dialect,
            seed=args.seed,
            redaction_mode=redaction_mode,
            redact_literals=True,
            strip_comments=True,
            llm_safe=True,
            obfuscate_qualifiers=True,
        ),
        instructions_text=_read_optional_template(args.instruction_template),
    )
    prepared = operation.prepared
    _render_sqlglot_diagnostics(operation.diagnostics)
    if prepared.safety.blockers and not args.expert_mode:
        _render_llm_safety_decision(
            safety=prepared.safety,
            llm_safe_requested=True,
        )
    elif prepared.safety.findings:
        _render_llm_safety_decision(
            safety=prepared.safety,
            llm_safe_requested=False,
        )

    _print_prepare_for_llm_summary(
        workspace_path=operation.workspace_path,
        redaction_mode=redaction_mode,
        manual_review_required=bool(prepared.safety.blockers and args.expert_mode),
    )
    if args.print_sql:
        print(prepared.snapshot.obfuscated_sql)
    return 0


def _print_prepare_for_llm_summary(
    *,
    workspace_path: Path,
    redaction_mode: str,
    manual_review_required: bool,
) -> None:
    print(f"Prepared LLM workflow workspace: {workspace_path}")
    if manual_review_required:
        print("Manual review required before sharing.")
        print("Review:")
        print(f"  {workspace_path / 'reports' / 'privacy_summary.json'}")
        print(f"  {workspace_path / 'reports' / 'llm_workflow_report.json'}")
        print("Send only after review:")
    else:
        print("Send these files:")
    print(f"  {workspace_path / 'obfuscated.sql'}")
    print(f"  {workspace_path / 'llm_instructions.md'}")
    print(f"Redaction: {redaction_mode}")
    print("Validation: manual-review-required" if manual_review_required else "Validation: passed")


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
    findings = list(safety.findings)
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


def _render_sqlglot_diagnostics(diagnostics: tuple[WorkflowDiagnostic, ...]) -> None:
    summary = summarize_sqlglot_diagnostics(diagnostics)
    if summary:
        print(summary, file=sys.stderr)


def _run_apply_llm_edits_command(args: argparse.Namespace) -> int:
    workspace_path = Path(args.workspace)
    operation = LocalWorkspaceApplication().apply_and_save_statement_replacements(
        workspace_path,
        load_llm_edits_payload(Path(args.edits)),
        output_path=Path(args.out) if args.out else None,
        persist=not args.dry_run,
    )
    result = operation.replacement
    summary = operation.summary.replacement
    _render_sqlglot_diagnostics(operation.diagnostics)

    print("apply-llm-edits summary:")
    print(f"applied_edit_count: {summary.applied_edit_count}")
    print(f"untouched_statement_count: {summary.untouched_statement_count}")
    print(f"statement_count: {summary.statement_count}")
    print(f"targeted_statement_ids: {list(summary.targeted_statement_ids)}")

    if args.dry_run:
        return 0

    print(result.applied_obfuscated_sql)
    return 0


def _run_restore_from_llm_command(args: argparse.Namespace) -> int:
    workspace_path = Path(args.workspace)
    application = LocalWorkspaceApplication()
    replacement_operation = application.apply_and_save_statement_replacements(
        workspace_path,
        load_llm_edits_payload(Path(args.edits)),
        persist=not args.dry_run,
    )
    applied_sql = replacement_operation.replacement.applied_obfuscated_sql

    if args.dry_run:
        deobfuscation_operation = application.analyze_deobfuscation(workspace_path, applied_sql)
        _render_sqlglot_diagnostics(
            (*replacement_operation.diagnostics, *deobfuscation_operation.diagnostics)
        )
        print("restore-from-llm dry-run summary:")
        _print_deobfuscation_summary(
            deobfuscation_operation.summary.deobfuscation,
            include_kind_breakdown=True,
        )
        if (
            deobfuscation_operation.summary.has_unresolved
            or deobfuscation_operation.summary.has_low_confidence
        ):
            return 1
        return 0

    try:
        deobfuscation_operation = application.validate_and_save_deobfuscation(
            workspace_path,
            applied_sql,
            output_path=Path(args.out) if args.out else None,
            allow_unresolved=bool(args.allow_unresolved),
            allow_low_confidence=bool(args.allow_low_confidence),
        )
    except DeobfuscationSafetyError as exc:
        _print_validate_before_write_summary(exc.result.summary)
        _render_sqlglot_diagnostics(exc.result.diagnostics)
        if exc.reason == "unresolved":
            raise WorkspaceError(
                "Validation failed: unresolved mappings found. "
                "Use --allow-unresolved to force output."
            ) from exc
        raise WorkspaceError(
            "Validation failed: low-confidence mappings found. "
            "Use --allow-low-confidence to force output."
        ) from exc

    _render_sqlglot_diagnostics(
        (*replacement_operation.diagnostics, *deobfuscation_operation.diagnostics)
    )
    restored_output_path = deobfuscation_operation.output_path or workspace_path / "deobfuscated.sql"
    applied_output_path = (
        replacement_operation.output_path or workspace_path / "llm_response_obfuscated.sql"
    )
    print(f"Restored LLM workflow output: {restored_output_path}")
    print(f"Applied obfuscated response: {applied_output_path}")
    print("Validation: passed")
    return 0


def _run_deobfuscate_command(args: argparse.Namespace) -> int:
    workspace_path = Path(args.workspace)
    edited_sql = _read_sql_file(Path(args.input))
    application = LocalWorkspaceApplication()
    if args.dry_run:
        operation = application.analyze_deobfuscation(workspace_path, edited_sql)
    else:
        try:
            operation = application.deobfuscate_and_save(
                workspace_path,
                edited_sql,
                output_path=Path(args.out) if args.out else None,
                allow_unresolved=bool(args.allow_unresolved),
                allow_low_confidence=bool(args.allow_low_confidence),
            )
        except DeobfuscationSafetyError as exc:
            _render_sqlglot_diagnostics(exc.result.diagnostics)
            if exc.reason == "unresolved":
                raise WorkspaceError(
                    "De-obfuscation found unresolved mappings. "
                    "Use --dry-run for diagnostics or pass --allow-unresolved to force output."
                ) from exc
            raise WorkspaceError(
                "De-obfuscation found low-confidence mappings. "
                "Use --dry-run for diagnostics or pass --allow-low-confidence to force output."
            ) from exc
    result = operation.deobfuscation
    operation_summary = operation.summary
    _render_sqlglot_diagnostics(operation.diagnostics)
    if args.dry_run:
        print("deobfuscate dry-run summary:")
        _print_deobfuscation_summary(operation_summary.deobfuscation, include_kind_breakdown=True)
        for recommendation in operation_summary.deobfuscation.recommendations:
            print(f"recommendation: {recommendation}")
        if operation_summary.has_unresolved:
            return 1
        return 0

    print(result.deobfuscated_sql)
    return 0


def _run_validate_before_write_command(args: argparse.Namespace) -> int:
    workspace_path = Path(args.workspace)
    edited_sql = _read_sql_file(Path(args.input))
    try:
        operation = LocalWorkspaceApplication().validate_and_save_deobfuscation(
            workspace_path,
            edited_sql,
            output_path=Path(args.out) if args.out else None,
            allow_unresolved=bool(args.allow_unresolved),
            allow_low_confidence=bool(args.allow_low_confidence),
        )
    except DeobfuscationSafetyError as exc:
        _print_validate_before_write_summary(exc.result.summary)
        _render_sqlglot_diagnostics(exc.result.diagnostics)
        if exc.reason == "unresolved":
            raise WorkspaceError(
                "Validation failed: unresolved mappings found. "
                "Use --allow-unresolved to force output."
            ) from exc
        raise WorkspaceError(
            "Validation failed: low-confidence mappings found. "
            "Use --allow-low-confidence to force output."
        ) from exc

    result = operation.deobfuscation
    _print_validate_before_write_summary(operation.summary.deobfuscation)
    _render_sqlglot_diagnostics(operation.diagnostics)

    print("validation passed: wrote de-obfuscated output")
    print(result.deobfuscated_sql)
    return 0


def _print_validate_before_write_summary(summary: DeobfuscationSummary) -> None:
    print("validate-before-write summary:")
    _print_deobfuscation_summary(summary, include_kind_breakdown=False)


def _print_deobfuscation_summary(
    summary: DeobfuscationSummary,
    *,
    include_kind_breakdown: bool,
) -> None:
    print(f"mapped_identifiers: {summary.mapped_identifiers}")
    print(f"unknown_count: {summary.unknown_count}")
    print(f"ambiguous_count: {summary.ambiguous_count}")
    print(f"low_confidence_count: {summary.low_confidence_count}")
    if include_kind_breakdown:
        print(f"unknown_by_kind: {summary.unknown_by_kind}")
        print(f"ambiguous_by_kind: {summary.ambiguous_by_kind}")
        print(f"low_confidence_by_kind: {summary.low_confidence_by_kind}")
    if summary.redaction_unknown_placeholder_count is not None:
        print(f"redaction_unknown_placeholder_count: {summary.redaction_unknown_placeholder_count}")
        print(f"redaction_missing_placeholder_count: {summary.redaction_missing_placeholder_count}")


def _run_roundtrip_command(args: argparse.Namespace) -> int:
    if args.stdout_only and args.output_dir:
        raise WorkspaceError("roundtrip: --stdout-only and --output-dir cannot be used together.")
    original_sql, input_path = _read_sql_source(args.sql_file)
    input_reference = input_path if input_path is not None else Path("stdin.sql")
    operation = LocalWorkspaceApplication().verify_and_save_roundtrip(
        original_sql,
        input_path=input_reference,
        workspace_path=Path(args.workspace) if args.workspace else None,
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
            obfuscate_qualifiers=bool(args.obfuscate_qualifiers),
        ),
        instructions_text=_read_optional_template(args.instruction_template),
        include_diff_report=bool(args.diff_report),
    )
    prepared = operation.prepared
    result = operation.roundtrip
    snapshot = prepared.snapshot
    _render_sqlglot_diagnostics(operation.diagnostics)
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
    print(deobfuscation.deobfuscated_sql)
    if deobfuscation.safety.has_unresolved or deobfuscation.safety.has_low_confidence:
        return 1
    return 0


def _run_workspace_info_command(args: argparse.Namespace) -> int:
    workspace_path = Path(args.workspace)
    inspection = LocalWorkspaceApplication().inspect_workspace(workspace_path)
    print(_format_workspace_inspection(inspection))
    return 0


def _format_workspace_inspection(inspection: WorkspaceInspection) -> str:
    lines = [
        f"workspace: {inspection.workspace_path}",
        f"dialect: {inspection.dialect}",
        f"seed: {inspection.seed}",
        f"pretty: {inspection.pretty}",
        f"batches: {inspection.batch_count}",
        f"statements: {inspection.statement_count}",
        f"statement anchors: {inspection.statement_anchor_count}",
        f"mapping entries: {inspection.mapping_entry_count}",
        f"mapping forward index size: {inspection.mapping_forward_index_size}",
        f"mapping reverse index size: {inspection.mapping_reverse_index_size}",
        f"integrity algorithm: {inspection.integrity_algorithm}",
        f"integrity tracked files: {inspection.integrity_tracked_file_count}",
    ]
    for artifact in inspection.artifact_statuses:
        lines.append(f"{artifact.relative_path}: {'yes' if artifact.available else 'no'}")
        if artifact.relative_path == "reports/privacy_summary.json":
            lines.append(
                "privacy llm-safe blocked: "
                f"{inspection.privacy_llm_safe_blocked if inspection.privacy_llm_safe_blocked is not None else 'n/a'}"
            )
            lines.append(
                "privacy review recommended: "
                f"{inspection.privacy_review_recommended if inspection.privacy_review_recommended is not None else 'n/a'}"
            )
    return "\n".join(lines)


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
    operation = LocalWorkspaceApplication().translate_and_save_artifacts(
        sql_text,
        options=TranslationOptions(
            source_dialect=args.source_dialect,
            target_dialect=args.target_dialect,
            pretty=args.pretty,
            validate=args.validate,
        ),
        workspace_path=Path(args.workspace) if args.workspace else None,
        persist_translated_sql=(
            args.out is None
            and not args.report_only
            and not args.stdout_only
        ),
    )
    workflow_result = operation.translation
    result = workflow_result.translation
    _render_sqlglot_diagnostics(operation.diagnostics)

    summary = operation.summary.translation
    print(
        "translate summary: "
        f"source={summary.source_dialect} "
        f"target={summary.target_dialect} "
        f"statements={summary.statement_count} "
        f"failed={summary.failed_statement_count} "
        f"warnings={summary.warning_count}"
    )

    if not operation.summary.succeeded:
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

    try:
        if args.command == "obfuscate":
            return _run_obfuscate_command(args)
        if args.command == "prepare-for-llm":
            return _run_prepare_for_llm_command(args)
        if args.command == "deobfuscate":
            return _run_deobfuscate_command(args)
        if args.command == "roundtrip":
            return _run_roundtrip_command(args)
        if args.command == "validate-before-write":
            return _run_validate_before_write_command(args)
        if args.command == "apply-llm-edits":
            return _run_apply_llm_edits_command(args)
        if args.command == "restore-from-llm":
            return _run_restore_from_llm_command(args)
        if args.command == "workspace-info":
            return _run_workspace_info_command(args)
        if args.command == "translate":
            return _run_translate_command(args)
        raise WorkspaceError(f"Unknown command: {args.command}")
    except (ObfuscatorError, ParseScriptError, WorkspaceError) as exc:
        presentation = present_application_error(exc)
        print(f"Error: {presentation.message}", file=sys.stderr)
        return 1
