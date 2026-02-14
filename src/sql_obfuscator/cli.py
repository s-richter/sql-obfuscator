from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .errors import InputFileError, ObfuscatorError, ParseScriptError
from .pipeline import obfuscate_sql


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="obfuscator.py",
        description="Obfuscate SQL identifiers in a T-SQL script.",
    )
    parser.add_argument("sql_file", help="Path to input .sql file")
    parser.add_argument("--dialect", default="tsql", help="sqlglot dialect (default: tsql)")
    parser.add_argument("--seed", type=int, default=None, help="Deterministic random seed")
    parser.add_argument(
        "--strict-go",
        action="store_true",
        help="Fail if batch separators cannot be handled safely",
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


def _write_output_file(path: Path, content: str) -> None:
    try:
        path.write_text(content, encoding="utf-8")
    except OSError as exc:
        raise InputFileError(f"Unable to write output file: {path}") from exc


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        input_path = Path(args.sql_file)
        sql_text = _read_sql_file(input_path)
        output_sql = obfuscate_sql(
            sql_text,
            dialect=args.dialect,
            seed=args.seed,
            strict_go=args.strict_go,
        )
        _write_output_file(_output_path_for_input(input_path), output_sql)
    except (ObfuscatorError, ParseScriptError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print(output_sql)
    return 0
