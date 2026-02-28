from __future__ import annotations

import re
from typing import Callable

from sqlglot import exp, parse
from sqlglot.expressions import Expression

_OUTPUT_INTO_QUALIFIED_RE = re.compile(
    r"(?is)(\bOUTPUT\b[\s\S]*?\bINTO\s+)"
    r"((?:\[[^\]]+\]|\w+)\s*\.\s*(?:\[[^\]]+\]|\w+))"
    r"(\s*\()"
)
_FOR_JSON_PATH_RE = re.compile(
    r"(?is)\bFOR\s+JSON\s+PATH(?:\s*,\s*[A-Z_]+(?:\s*\([^)]*\))?)*"
)
_FOR_JSON_EMITTED_RE = re.compile(
    r"(?is)FOR\s+XML\s+PATH\('(?P<name>__SQLGLOT_FOR_JSON_\d+__)'\)"
)
_RAW_STMT_EMITTED_RE = re.compile(
    r"(?is)SELECT\s+'(?P<name>__SQLGLOT_RAW_STMT_\d+__)'\s+AS\s+\[(?P=name)\];?"
)
_RAW_STMT_PREFIX = "__SQLGLOT_RAW_STMT_"
_FOR_JSON_PREFIX = "__SQLGLOT_FOR_JSON_"


def parse_sql(
    sql: str,
    *,
    dialect: str,
    parse_func: Callable[..., list[Expression]] = parse,
) -> list[Expression]:
    if dialect.lower() != "tsql":
        return [statement for statement in parse_func(sql, dialect=dialect) if statement is not None]

    rewritten_sql, replacements = _rewrite_tsql_output_into_targets(sql)
    rewritten_sql, raw_statement_replacements = _rewrite_tsql_raw_statements(rewritten_sql)
    rewritten_sql, emit_replacements = _rewrite_tsql_for_json_clauses(rewritten_sql)
    statements = [statement for statement in parse_func(rewritten_sql, dialect=dialect) if statement is not None]
    if replacements or raw_statement_replacements or emit_replacements:
        for statement in statements:
            _restore_tsql_output_into_targets(statement, replacements)
            _restore_tsql_raw_statement(statement, raw_statement_replacements)
            _set_emit_replacements(statement, emit_replacements)
            _set_raw_statement_replacements(statement, raw_statement_replacements)
    return statements


def emit_sql(
    statement: Expression,
    *,
    dialect: str,
    pretty: bool,
    strip_comments: bool = False,
) -> str:
    raw_sql = statement.meta.get("raw_sql")
    if isinstance(raw_sql, str):
        return raw_sql

    rendered = statement.transform(
        lambda node: _canonicalize_tsql_json_fallback(node, dialect=dialect),
        copy=True,
    )
    if strip_comments:
        for node in rendered.walk():
            if hasattr(node, "comments"):
                node.comments = None
    sql_text = rendered.sql(dialect=dialect, pretty=pretty)
    replacements = statement.meta.get("emit_replacements")
    if isinstance(replacements, dict):
        sql_text = _FOR_JSON_EMITTED_RE.sub(
            lambda match: replacements.get(match.group("name"), match.group(0)),
            sql_text,
        )
        for placeholder, original in replacements.items():
            sql_text = sql_text.replace(placeholder, original)
    raw_stmt_replacements = statement.meta.get("raw_stmt_replacements")
    if isinstance(raw_stmt_replacements, dict):
        sql_text = _RAW_STMT_EMITTED_RE.sub(
            lambda match: raw_stmt_replacements.get(match.group("name"), match.group(0)),
            sql_text,
        )
    return sql_text


def join_emitted_statements(statements: list[str]) -> str:
    if not statements:
        return ""

    chunks = [statements[0]]
    for statement_sql in statements[1:]:
        previous = chunks[-1].rstrip()
        separator = "\n" if previous.endswith(";") else ";\n"
        chunks.append(separator)
        chunks.append(statement_sql)
    return "".join(chunks)


def _rewrite_tsql_output_into_targets(sql: str) -> tuple[str, dict[str, str]]:
    replacements: dict[str, str] = {}

    def _replace(match: re.Match[str]) -> str:
        placeholder = f"__SQLGLOT_OUTPUT_INTO_TARGET_{len(replacements) + 1}__"
        qualified_name = match.group(2)
        replacements[placeholder.upper()] = qualified_name
        return f"{match.group(1)}{placeholder}{match.group(3)}"

    return _OUTPUT_INTO_QUALIFIED_RE.sub(_replace, sql), replacements


def _restore_tsql_output_into_targets(statement: Expression, replacements: dict[str, str]) -> None:
    for node in statement.walk():
        if not isinstance(node, exp.Returning):
            continue
        into = node.args.get("into")
        if not isinstance(into, exp.Anonymous):
            continue
        target_name = into.this
        if not isinstance(target_name, str):
            continue
        qualified_name = replacements.get(target_name.upper())
        if qualified_name is None:
            continue
        into.set("this", qualified_name)


def _rewrite_tsql_raw_statements(sql: str) -> tuple[str, dict[str, str]]:
    replacements: dict[str, str] = {}
    rewritten_lines: list[str] = []
    lines = sql.splitlines(keepends=True)
    index = 0
    while index < len(lines):
        stripped = lines[index].strip()
        raw_sql: str | None = None
        next_index = index + 1
        if stripped.upper().startswith("SAVE TRANSACTION "):
            raw_sql = lines[index]
        elif stripped.upper().startswith("WAITFOR DELAY "):
            raw_sql = lines[index]
        elif stripped.upper().startswith("OPEN "):
            raw_sql = lines[index]
        elif stripped.upper().startswith("CLOSE "):
            raw_sql = lines[index]
        elif stripped.upper().startswith("DEALLOCATE "):
            raw_sql = lines[index]
        elif stripped.upper().startswith("WHILE "):
            raw_sql, next_index = _consume_begin_end_block(lines, index)
        elif stripped.upper().startswith("IF CURSOR_STATUS("):
            raw_sql, next_index = _consume_begin_end_block(lines, index)
        elif stripped.upper().startswith("IF XACT_STATE("):
            raw_sql, next_index = _consume_if_chain(lines, index)
        elif stripped.upper().startswith("IF "):
            raw_sql, next_index = _consume_if_begin_end_block(lines, index)

        if raw_sql is None:
            rewritten_lines.append(lines[index])
            index += 1
            continue

        placeholder = f"{_RAW_STMT_PREFIX}{len(replacements) + 1}__"
        normalized_raw_sql = raw_sql.rstrip("\r\n")
        replacements[placeholder] = normalized_raw_sql
        rewritten_lines.append(
            f"SELECT '{placeholder}' AS [{placeholder}];{_line_ending(raw_sql)}"
        )
        index = next_index
    return "".join(rewritten_lines), replacements


def _rewrite_tsql_for_json_clauses(sql: str) -> tuple[str, dict[str, str]]:
    replacements: dict[str, str] = {}

    def _replace(match: re.Match[str]) -> str:
        placeholder = f"{_FOR_JSON_PREFIX}{len(replacements) + 1}__"
        marker = f"FOR XML PATH('{placeholder}')"
        replacements[placeholder] = match.group(0)
        return marker

    return _FOR_JSON_PATH_RE.sub(_replace, sql), replacements


def _consume_begin_end_block(lines: list[str], start_index: int) -> tuple[str, int]:
    index = start_index
    begin_depth = 0
    saw_begin = False
    while index < len(lines):
        stripped = lines[index].strip().upper()
        if stripped in {"BEGIN", "BEGIN;"}:
            begin_depth += 1
            saw_begin = True
        elif stripped.startswith("END"):
            if saw_begin:
                begin_depth -= 1
                if begin_depth == 0:
                    index += 1
                    break
        index += 1
    return "".join(lines[start_index:index]), index


def _consume_if_chain(lines: list[str], start_index: int) -> tuple[str, int]:
    index = start_index
    while index < len(lines):
        current = lines[index].strip().upper()
        if index == start_index:
            if not current.startswith("IF XACT_STATE("):
                break
        elif not current.startswith("ELSE IF") and not current.startswith("ELSE"):
            break
        index += 1
        while index < len(lines):
            raw_line = lines[index]
            stripped = raw_line.strip().upper()
            if not stripped:
                index += 1
                continue
            if stripped.startswith("ELSE IF") or stripped.startswith("ELSE"):
                break
            if not raw_line.startswith((" ", "\t")):
                break
            index += 1
    return "".join(lines[start_index:index]), index


def _consume_if_begin_end_block(lines: list[str], start_index: int) -> tuple[str | None, int]:
    probe = start_index
    saw_begin = False
    while probe < len(lines):
        stripped = lines[probe].strip().upper()
        if probe == start_index:
            if not stripped.startswith("IF "):
                return None, start_index + 1
        elif stripped in {"BEGIN", "BEGIN;"}:
            saw_begin = True
            break
        elif not stripped or _looks_like_if_condition_continuation(stripped):
            probe += 1
            continue
        else:
            return None, start_index + 1
        probe += 1

    if not saw_begin:
        return None, start_index + 1
    return _consume_begin_end_block(lines, start_index)


def _looks_like_if_condition_continuation(stripped: str) -> bool:
    return (
        stripped in {"(", ")"}
        or stripped.startswith("SELECT")
        or stripped.startswith("FROM")
        or stripped.startswith("WHERE")
        or stripped.startswith("AND ")
        or stripped.startswith("OR ")
        or stripped.startswith("EXISTS")
        or stripped.startswith("NOT ")
    )


def _line_ending(text: str) -> str:
    if text.endswith("\r\n"):
        return "\r\n"
    if text.endswith("\n"):
        return "\n"
    return ""


def _restore_tsql_raw_statement(statement: Expression, replacements: dict[str, str]) -> None:
    placeholder = _raw_statement_placeholder_name(statement)
    if placeholder is None:
        return
    raw_sql = replacements.get(placeholder)
    if raw_sql is None:
        return
    statement.meta["raw_sql"] = raw_sql


def _raw_statement_placeholder_name(statement: Expression) -> str | None:
    if not isinstance(statement, exp.Select):
        return None
    if len(statement.expressions) != 1:
        return None
    alias = statement.expressions[0]
    if not isinstance(alias, exp.Alias):
        return None
    literal = alias.this
    alias_id = alias.args.get("alias")
    if not isinstance(literal, exp.Literal) or not literal.is_string:
        return None
    if not isinstance(alias_id, exp.Identifier):
        return None
    if literal.this != alias_id.name:
        return None
    if not str(literal.this).startswith(_RAW_STMT_PREFIX):
        return None
    return str(literal.this)


def _set_emit_replacements(statement: Expression, replacements: dict[str, str]) -> None:
    if not replacements:
        return
    existing = statement.meta.get("emit_replacements")
    merged: dict[str, str] = {}
    if isinstance(existing, dict):
        merged.update(existing)
    merged.update(replacements)
    statement.meta["emit_replacements"] = merged


def _set_raw_statement_replacements(statement: Expression, replacements: dict[str, str]) -> None:
    if replacements:
        statement.meta["raw_stmt_replacements"] = replacements


def _canonicalize_tsql_json_fallback(node: Expression, *, dialect: str) -> Expression:
    if dialect.lower() != "tsql":
        return node
    if not isinstance(node, exp.Coalesce):
        return node
    if not node.args.get("is_null"):
        return node
    if len(node.expressions) != 1:
        return node
    left = node.this
    right = node.expressions[0]
    if not isinstance(left, exp.JSONExtract):
        return node
    if not isinstance(right, exp.JSONExtractScalar):
        return node
    if not _same_json_extract_target(left, right):
        return node
    return left


def _same_json_extract_target(left: exp.JSONExtract, right: exp.JSONExtractScalar) -> bool:
    return (
        left.args.get("this") == right.args.get("this")
        and left.args.get("expression") == right.args.get("expression")
    )
