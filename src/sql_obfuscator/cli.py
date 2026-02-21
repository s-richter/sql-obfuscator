from __future__ import annotations

import argparse
import difflib
import sys
from dataclasses import asdict
from pathlib import Path

from sqlglot import parse
from sqlglot.errors import ParseError

from .dialects_factory import get_dialect_profile, supported_dialects
from .deobfuscation import deobfuscate_sql_with_report
from .errors import InputFileError, ObfuscatorError, ParseScriptError, WorkspaceError
from .pipeline import obfuscate_sql_with_metadata
from .redaction import restore_reversible_redaction
from .translation import translate_sql_with_report
from .workspace import (
    default_workspace_path,
    load_context_payload,
    load_mapping_payload,
    load_redaction_payload,
    save_deobfuscation_artifacts,
    save_roundtrip_reports,
    save_translation_artifacts,
    save_workspace_artifacts,
    validate_workspace_integrity,
)


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
        help="Fail if batch separators cannot be handled safely",
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


def _validate_redaction_args(args: argparse.Namespace) -> None:
    uses_redaction_flags = bool(args.strip_comments or args.redact_literals)
    if args.redaction_mode == "none" and uses_redaction_flags:
        raise WorkspaceError(
            "Redaction flags require --redaction-mode irreversible or --redaction-mode reversible."
        )


def build_command_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="obfuscator.py",
        description="SQL obfuscation workspace commands.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    obfuscate_parser = subparsers.add_parser(
        "obfuscate",
        help="Obfuscate a SQL script and persist workspace artifacts",
    )
    obfuscate_parser.add_argument("sql_file", help="Path to input .sql file")
    _add_common_obfuscation_args(obfuscate_parser)

    deobfuscate_parser = subparsers.add_parser(
        "deobfuscate",
        help="De-obfuscate an edited obfuscated SQL script using workspace artifacts",
    )
    deobfuscate_parser.add_argument(
        "--workspace",
        required=True,
        help="Path to workspace folder created during obfuscation",
    )
    deobfuscate_parser.add_argument(
        "--input",
        required=True,
        help="Path to edited obfuscated SQL script",
    )
    deobfuscate_parser.add_argument(
        "--out",
        default=None,
        help="Optional output path for de-obfuscated SQL",
    )
    deobfuscate_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Analyze de-obfuscation and print report summary without writing files",
    )
    deobfuscate_parser.add_argument(
        "--allow-unresolved",
        action="store_true",
        help="Allow unknown/ambiguous mappings in non-dry-run mode and still write outputs",
    )

    roundtrip_parser = subparsers.add_parser(
        "roundtrip",
        help="Obfuscate and immediately de-obfuscate for verification",
    )
    roundtrip_parser.add_argument("sql_file", help="Path to input .sql file")
    _add_common_obfuscation_args(roundtrip_parser)
    roundtrip_parser.add_argument(
        "--diff-report",
        action="store_true",
        help="Reserved for future roundtrip diff reporting",
    )

    translate_parser = subparsers.add_parser(
        "translate",
        help="Translate SQL between supported dialects",
    )
    translate_parser.add_argument(
        "--input",
        required=True,
        help="Path to input .sql file",
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


def _output_path_for_input(path: Path) -> Path:
    if path.suffix:
        return path.with_name(f"{path.stem}_obfuscated{path.suffix}")
    return path.with_name(f"{path.name}_obfuscated")


def _translation_output_path_for_input(path: Path, *, target_dialect: str) -> Path:
    if path.suffix:
        return path.with_name(f"{path.stem}_{target_dialect}{path.suffix}")
    return path.with_name(f"{path.name}_{target_dialect}.sql")


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


def _normalize_sql_for_comparison(sql_text: str, *, dialect: str) -> str:
    profile = get_dialect_profile(dialect)
    normalized_batches: list[str] = []
    for batch in profile.split_batches(sql_text):
        if not batch.strip():
            normalized_batches.append(batch)
            continue
        statements = parse(batch, dialect=dialect)
        normalized_batches.append(";\n".join(stmt.sql(dialect=dialect, pretty=True) for stmt in statements))
    return profile.join_batches(normalized_batches)


def _run_obfuscate_command(args: argparse.Namespace) -> int:
    _validate_redaction_args(args)
    input_path = Path(args.sql_file)
    sql_text = _read_sql_file(input_path)
    result = obfuscate_sql_with_metadata(
        sql_text,
        dialect=args.dialect,
        seed=args.seed,
        strict_go=args.strict_go,
        pretty=args.pretty,
        redact_literals=args.redact_literals,
        strip_comments=args.strip_comments,
        redaction_mode=args.redaction_mode,
    )
    output_sql = result.output_sql
    _write_output_file(_output_path_for_input(input_path), output_sql)
    llm_instructions_text = _read_optional_template(args.instruction_template)

    workspace_path = Path(args.workspace) if args.workspace else default_workspace_path(input_path)
    save_workspace_artifacts(
        workspace_path=workspace_path,
        input_path=input_path,
        original_sql=sql_text,
        obfuscated_sql=output_sql,
        mapping_payload=result.mapping_payload,
        context_payload=result.context_payload,
        llm_instructions_text=llm_instructions_text,
        redaction_payload=result.redaction_payload,
    )
    # Validate schema and data shape immediately after write.
    load_mapping_payload(workspace_path / "mapping.json")
    load_context_payload(workspace_path / "context.json")
    validate_workspace_integrity(workspace_path)

    print(output_sql)
    return 0


def _run_deobfuscate_command(args: argparse.Namespace) -> int:
    workspace_path = Path(args.workspace)
    validate_workspace_integrity(workspace_path)
    mapping_payload = load_mapping_payload(workspace_path / "mapping.json")
    context_payload = load_context_payload(workspace_path / "context.json")
    input_path = Path(args.input)
    edited_sql = _read_sql_file(input_path)

    deobfuscated_sql, report = deobfuscate_sql_with_report(
        edited_sql,
        mapping_payload=mapping_payload,
        context_payload=context_payload,
    )
    redaction_path = workspace_path / "redaction.json"
    redaction_report: dict | None = None
    if redaction_path.exists():
        redaction_payload = load_redaction_payload(redaction_path)
        deobfuscated_sql, redaction_report = restore_reversible_redaction(
            deobfuscated_sql,
            dialect=context_payload.get("dialect", "tsql"),
            pretty=bool(context_payload.get("pretty", True)),
            redaction_payload=redaction_payload,
        )
        report["redaction"] = redaction_report

    redaction_unresolved = False
    if redaction_report is not None:
        redaction_unresolved = (
            redaction_report.get("unknown_placeholder_count", 0) > 0
            or redaction_report.get("missing_placeholder_count", 0) > 0
        )
    has_unresolved = report.get("unknown_count", 0) > 0 or report.get("ambiguous_count", 0) > 0
    has_unresolved = has_unresolved or redaction_unresolved
    if args.dry_run:
        print("deobfuscate dry-run summary:")
        print(f"mapped_identifiers: {report.get('mapped_identifiers', 0)}")
        print(f"unknown_count: {report.get('unknown_count', 0)}")
        print(f"ambiguous_count: {report.get('ambiguous_count', 0)}")
        print(f"low_confidence_count: {report.get('low_confidence_count', 0)}")
        print(f"unknown_by_kind: {report.get('unknown_by_kind', {})}")
        print(f"ambiguous_by_kind: {report.get('ambiguous_by_kind', {})}")
        print(f"low_confidence_by_kind: {report.get('low_confidence_by_kind', {})}")
        if redaction_report is not None:
            print(f"redaction_unknown_placeholder_count: {redaction_report.get('unknown_placeholder_count', 0)}")
            print(f"redaction_missing_placeholder_count: {redaction_report.get('missing_placeholder_count', 0)}")
        for recommendation in report.get("recommendations", []):
            print(f"recommendation: {recommendation}")
        if has_unresolved:
            return 1
        return 0

    if has_unresolved and not args.allow_unresolved:
        raise WorkspaceError(
            "De-obfuscation found unresolved mappings. "
            "Use --dry-run for diagnostics or pass --allow-unresolved to force output."
        )

    output_path = Path(args.out) if args.out else workspace_path / "deobfuscated.sql"
    _write_output_file(output_path, deobfuscated_sql)
    save_deobfuscation_artifacts(
        workspace_path=workspace_path,
        deobfuscated_sql=deobfuscated_sql,
        report_payload=report,
    )
    print(deobfuscated_sql)
    return 0


def _run_roundtrip_command(args: argparse.Namespace) -> int:
    _validate_redaction_args(args)
    input_path = Path(args.sql_file)
    original_sql = _read_sql_file(input_path)

    obfuscation = obfuscate_sql_with_metadata(
        original_sql,
        dialect=args.dialect,
        seed=args.seed,
        strict_go=args.strict_go,
        pretty=args.pretty,
        redact_literals=args.redact_literals,
        strip_comments=args.strip_comments,
        redaction_mode=args.redaction_mode,
    )
    obfuscated_sql = obfuscation.output_sql
    _write_output_file(_output_path_for_input(input_path), obfuscated_sql)
    llm_instructions_text = _read_optional_template(args.instruction_template)

    workspace_path = Path(args.workspace) if args.workspace else default_workspace_path(input_path)
    save_workspace_artifacts(
        workspace_path=workspace_path,
        input_path=input_path,
        original_sql=original_sql,
        obfuscated_sql=obfuscated_sql,
        mapping_payload=obfuscation.mapping_payload,
        context_payload=obfuscation.context_payload,
        llm_instructions_text=llm_instructions_text,
        redaction_payload=obfuscation.redaction_payload,
    )
    mapping_payload = load_mapping_payload(workspace_path / "mapping.json")
    context_payload = load_context_payload(workspace_path / "context.json")
    validate_workspace_integrity(workspace_path)

    deobfuscated_sql, deobfuscation_report = deobfuscate_sql_with_report(
        obfuscated_sql,
        mapping_payload=mapping_payload,
        context_payload=context_payload,
    )
    redaction_path = workspace_path / "redaction.json"
    if redaction_path.exists():
        redaction_payload = load_redaction_payload(redaction_path)
        deobfuscated_sql, redaction_report = restore_reversible_redaction(
            deobfuscated_sql,
            dialect=context_payload.get("dialect", "tsql"),
            pretty=bool(context_payload.get("pretty", True)),
            redaction_payload=redaction_payload,
        )
        deobfuscation_report["redaction"] = redaction_report
    save_deobfuscation_artifacts(
        workspace_path=workspace_path,
        deobfuscated_sql=deobfuscated_sql,
        report_payload=deobfuscation_report,
    )

    diff_lines = list(
        difflib.unified_diff(
            original_sql.splitlines(keepends=True),
            deobfuscated_sql.splitlines(keepends=True),
            fromfile="original.sql",
            tofile="deobfuscated.sql",
        )
    )

    dialect = context_payload.get("dialect", "tsql")
    try:
        original_pretty_sql = _normalize_sql_for_comparison(original_sql, dialect=dialect)
        deobfuscated_pretty_sql = _normalize_sql_for_comparison(deobfuscated_sql, dialect=dialect)
    except ParseError as exc:
        raise ParseScriptError(f"Parse error while building normalized roundtrip comparison: {exc}") from exc

    normalized_diff_lines = list(
        difflib.unified_diff(
            original_pretty_sql.splitlines(keepends=True),
            deobfuscated_pretty_sql.splitlines(keepends=True),
            fromfile="reports/original_pretty.sql",
            tofile="reports/deobfuscated_pretty.sql",
        )
    )

    roundtrip_report = {
        "schema_version": 1,
        "exact_match": original_sql == deobfuscated_sql,
        "original_char_count": len(original_sql),
        "deobfuscated_char_count": len(deobfuscated_sql),
        "diff_line_count": len(diff_lines),
        "normalized_exact_match": original_pretty_sql == deobfuscated_pretty_sql,
        "normalized_original_char_count": len(original_pretty_sql),
        "normalized_deobfuscated_char_count": len(deobfuscated_pretty_sql),
        "normalized_diff_line_count": len(normalized_diff_lines),
        "deobfuscation_report": deobfuscation_report,
    }
    save_roundtrip_reports(
        workspace_path=workspace_path,
        report_payload=roundtrip_report,
        diff_text="".join(diff_lines) if args.diff_report else None,
        original_pretty_sql=original_pretty_sql,
        deobfuscated_pretty_sql=deobfuscated_pretty_sql,
        normalized_diff_text="".join(normalized_diff_lines),
    )

    print(deobfuscated_sql)
    if deobfuscation_report.get("unknown_count", 0) > 0:
        return 1
    if deobfuscation_report.get("ambiguous_count", 0) > 0:
        return 1
    redaction_report = deobfuscation_report.get("redaction")
    if isinstance(redaction_report, dict):
        if redaction_report.get("unknown_placeholder_count", 0) > 0:
            return 1
        if redaction_report.get("missing_placeholder_count", 0) > 0:
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

    lines = [
        f"workspace: {workspace_path}",
        f"dialect: {context_payload.get('dialect')}",
        f"seed: {context_payload.get('seed')}",
        f"pretty: {context_payload.get('pretty')}",
        f"batches: {context_payload.get('batch_count')}",
        f"statements: {context_payload.get('statement_count')}",
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
    input_path = Path(args.input)
    sql_text = _read_sql_file(input_path)
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

    if args.workspace:
        workspace_path = Path(args.workspace)
        save_translation_artifacts(
            workspace_path=workspace_path,
            report_payload=asdict(result),
            translated_sql=result.output_sql if args.out is None and not args.report_only else None,
        )

    if result.failed_statement_count > 0:
        return 1
    if args.validate and not result.validated:
        return 1
    if args.report_only:
        return 0

    output_path = (
        Path(args.out)
        if args.out
        else _translation_output_path_for_input(input_path, target_dialect=args.target_dialect)
    )
    _write_output_file(output_path, result.output_sql)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_command_parser()
    args = parser.parse_args(argv)

    try:
        if args.command == "obfuscate":
            return _run_obfuscate_command(args)
        if args.command == "deobfuscate":
            return _run_deobfuscate_command(args)
        if args.command == "roundtrip":
            return _run_roundtrip_command(args)
        if args.command == "workspace-info":
            return _run_workspace_info_command(args)
        if args.command == "translate":
            return _run_translate_command(args)
        raise WorkspaceError(f"Unknown command: {args.command}")
    except (ObfuscatorError, ParseScriptError, WorkspaceError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
