from __future__ import annotations

from collections.abc import Sequence

from sqlglot import Tokenizer, exp
from sqlglot.expressions import Expression

from .dialects_base import DialectProfile
from .registry import IdentifierRegistry


def _identifier_name(identifier: exp.Identifier | None) -> str | None:
    if not isinstance(identifier, exp.Identifier):
        return None
    return identifier.name


def _node_context(
    node: Expression, *, batch_index: int, statement_index: int
) -> dict[str, str | int]:
    parent_kind = type(node.parent).__name__.lower() if isinstance(node.parent, Expression) else ""
    node_kind = type(node).__name__.lower()
    arg_key = node.arg_key or ""
    clause_kind = _clause_kind(node)
    statement_kind = _statement_kind(node)
    return {
        "batch_index": batch_index,
        "statement_index": statement_index,
        "scope_id": f"b{batch_index}.s{statement_index}.{node_kind}.{arg_key}",
        "parent_kind": parent_kind,
        "statement_kind": statement_kind,
        "clause_kind": clause_kind,
        "node_kind": node_kind,
        "arg_key": arg_key,
    }


def _clause_kind(node: Expression) -> str:
    parent = node.parent
    while isinstance(parent, Expression):
        if isinstance(
            parent,
            (
                exp.Select,
                exp.From,
                exp.Where,
                exp.Join,
                exp.Group,
                exp.Order,
                exp.Having,
                exp.Qualify,
                exp.Insert,
                exp.Update,
                exp.Delete,
                exp.Create,
            ),
        ):
            return type(parent).__name__.lower()
        parent = parent.parent
    return ""


def _statement_kind(node: Expression) -> str:
    parent: Expression | None = node
    while isinstance(parent, Expression):
        if isinstance(
            parent,
            (
                exp.Select,
                exp.Insert,
                exp.Update,
                exp.Delete,
                exp.Create,
                exp.Merge,
            ),
        ):
            return type(parent).__name__.lower()
        parent = parent.parent
    return ""


def _is_update_alias_target(table: exp.Table) -> bool:
    if not isinstance(table.parent, exp.Update) or table.arg_key != "this":
        return False

    table_name = _identifier_name(table.this)
    if not table_name:
        return False

    alias_names = {
        alias.this.name
        for alias in table.parent.find_all(exp.TableAlias)
        if isinstance(alias.this, exp.Identifier)
    }
    return table_name in alias_names


def _rename_table(
    table: exp.Table,
    registry: IdentifierRegistry,
    profile: DialectProfile,
    *,
    batch_index: int,
    statement_index: int,
) -> exp.Table:
    context = _node_context(table, batch_index=batch_index, statement_index=statement_index)
    identifier = table.this
    if not isinstance(identifier, exp.Identifier):
        return table

    if _is_update_alias_target(table):
        # UPDATE alias target should follow alias obfuscation, not table-name obfuscation.
        identifier.set(
            "this",
            registry.get_or_create(
                identifier.name,
                kind="alias",
                role="update_target_alias",
                **context,
            ),
        )
        return table

    renamed = registry.get_or_create(
        profile.table_identifier_raw(identifier),
        kind="table",
        role="table_reference",
        **context,
    )
    identifier.set("this", profile.table_identifier_ast_value(renamed))
    return table


def _rename_column(
    column: exp.Column,
    registry: IdentifierRegistry,
    *,
    batch_index: int,
    statement_index: int,
) -> exp.Column:
    context = _node_context(column, batch_index=batch_index, statement_index=statement_index)
    identifier = column.this
    if isinstance(identifier, exp.Identifier):
        identifier.set(
            "this",
            registry.get_or_create(
                identifier.name,
                kind="column",
                role="column_reference",
                **context,
            ),
        )

    table_identifier = column.args.get("table")
    if isinstance(table_identifier, exp.Identifier):
        table_identifier.set(
            "this",
            registry.get_or_create(
                table_identifier.name,
                kind="alias",
                role="column_qualifier",
                **context,
            ),
        )

    return column


def _rename_cte(
    cte: exp.CTE,
    registry: IdentifierRegistry,
    *,
    batch_index: int,
    statement_index: int,
) -> exp.CTE:
    context = _node_context(cte, batch_index=batch_index, statement_index=statement_index)
    alias = cte.args.get("alias")
    if not isinstance(alias, exp.TableAlias) or not isinstance(alias.this, exp.Identifier):
        return cte
    alias.this.set(
        "this",
        registry.get_or_create(
            alias.this.name,
            kind="cte",
            role="cte_alias",
            **context,
        ),
    )
    return cte


def _rename_table_alias(
    table_alias: exp.TableAlias,
    registry: IdentifierRegistry,
    *,
    batch_index: int,
    statement_index: int,
) -> exp.TableAlias:
    context = _node_context(table_alias, batch_index=batch_index, statement_index=statement_index)
    # CTE declaration alias is handled in _rename_cte.
    if isinstance(table_alias.parent, exp.CTE):
        return table_alias

    alias_identifier = table_alias.this
    if isinstance(alias_identifier, exp.Identifier):
        alias_identifier.set(
            "this",
            registry.get_or_create(
                alias_identifier.name,
                kind="alias",
                role="table_alias",
                **context,
            ),
        )

    for identifier in table_alias.args.get("columns") or []:
        if isinstance(identifier, exp.Identifier):
            identifier.set(
                "this",
                registry.get_or_create(
                    identifier.name,
                    kind="column_alias",
                    role="table_alias_column",
                    **context,
                ),
            )

    return table_alias


def _rename_expression_alias(
    alias: exp.Alias,
    registry: IdentifierRegistry,
    *,
    batch_index: int,
    statement_index: int,
) -> exp.Alias:
    context = _node_context(alias, batch_index=batch_index, statement_index=statement_index)
    alias_identifier = alias.args.get("alias")
    if isinstance(alias_identifier, exp.Identifier):
        alias_identifier.set(
            "this",
            registry.get_or_create(
                alias_identifier.name,
                kind="column_alias",
                role="projection_alias",
                **context,
            ),
        )
    return alias


def _rename_column_def(
    column_def: exp.ColumnDef,
    registry: IdentifierRegistry,
    *,
    batch_index: int,
    statement_index: int,
    type_lexemes_by_start: dict[int, str],
) -> exp.ColumnDef:
    context = _node_context(column_def, batch_index=batch_index, statement_index=statement_index)
    identifier = column_def.this
    if not isinstance(identifier, exp.Identifier):
        return column_def
    type_lexeme = _column_def_type_lexeme(column_def, type_lexemes_by_start)
    identifier.set(
        "this",
        registry.get_or_create(
            identifier.name,
            kind="column_def",
            role="column_definition",
            type_lexeme=type_lexeme,
            **context,
        ),
    )
    return column_def


def _rename_insert_column_list(
    schema: exp.Schema,
    registry: IdentifierRegistry,
    *,
    batch_index: int,
    statement_index: int,
) -> exp.Schema:
    context = _node_context(schema, batch_index=batch_index, statement_index=statement_index)
    if not isinstance(schema.parent, exp.Insert) or schema.arg_key != "this":
        return schema
    for identifier in schema.expressions:
        if isinstance(identifier, exp.Identifier):
            identifier.set(
                "this",
                registry.get_or_create(
                    identifier.name,
                    kind="insert_column",
                    role="insert_target_column",
                    **context,
                ),
            )
    return schema


def transform_statements(
    statements: Sequence[Expression],
    *,
    registry: IdentifierRegistry,
    profile: DialectProfile,
    batch_index: int,
    batch_sql: str,
    dialect: str,
) -> list[Expression]:
    transformed: list[Expression] = []
    type_lexemes_by_start = _column_type_lexemes_by_start(batch_sql, dialect=dialect)

    for statement_index, statement in enumerate(statements, start=1):
        def _transform(node: Expression) -> Expression:
            if isinstance(node, exp.Table):
                return _rename_table(
                    node,
                    registry,
                    profile,
                    batch_index=batch_index,
                    statement_index=statement_index,
                )
            if isinstance(node, exp.Column):
                return _rename_column(
                    node,
                    registry,
                    batch_index=batch_index,
                    statement_index=statement_index,
                )
            if isinstance(node, exp.CTE):
                return _rename_cte(
                    node,
                    registry,
                    batch_index=batch_index,
                    statement_index=statement_index,
                )
            if isinstance(node, exp.TableAlias):
                return _rename_table_alias(
                    node,
                    registry,
                    batch_index=batch_index,
                    statement_index=statement_index,
                )
            if isinstance(node, exp.Alias):
                return _rename_expression_alias(
                    node,
                    registry,
                    batch_index=batch_index,
                    statement_index=statement_index,
                )
            if isinstance(node, exp.ColumnDef):
                return _rename_column_def(
                    node,
                    registry,
                    batch_index=batch_index,
                    statement_index=statement_index,
                    type_lexemes_by_start=type_lexemes_by_start,
                )
            if isinstance(node, exp.Schema):
                return _rename_insert_column_list(
                    node,
                    registry,
                    batch_index=batch_index,
                    statement_index=statement_index,
                )
            return node

        transformed.append(statement.transform(_transform, copy=True))

    return transformed


def _column_type_lexemes_by_start(batch_sql: str, *, dialect: str) -> dict[int, str]:
    tokens = Tokenizer(dialect=dialect).tokenize(batch_sql)
    token_index_by_start = {token.start: idx for idx, token in enumerate(tokens)}
    type_lexemes_by_start: dict[int, str] = {}

    for idx, token in enumerate(tokens):
        if token.text != "(":
            continue

        cursor = idx + 1
        while cursor < len(tokens):
            current = tokens[cursor]
            if current.text == ")":
                break
            if current.text == ",":
                cursor += 1
                continue

            # Expected shape: <column_name> <type_keyword> ...
            column_name_start = current.start
            if cursor + 1 >= len(tokens):
                break
            type_token = tokens[cursor + 1]
            if not _looks_like_type_keyword(type_token.text):
                cursor += 1
                continue

            type_lexemes_by_start[column_name_start] = type_token.text

            cursor += 2
            while cursor < len(tokens):
                tail = tokens[cursor].text
                if tail == "," or tail == ")":
                    break
                cursor += 1
            continue

    # Keep only entries that correspond to real token starts.
    return {
        start: lexeme
        for start, lexeme in type_lexemes_by_start.items()
        if start in token_index_by_start
    }


def _column_def_type_lexeme(
    column_def: exp.ColumnDef,
    type_lexemes_by_start: dict[int, str],
) -> str | None:
    identifier = column_def.this
    if not isinstance(identifier, exp.Identifier):
        return None

    start = identifier.meta.get("start")
    if not isinstance(start, int):
        return None
    return type_lexemes_by_start.get(start)


def _looks_like_type_keyword(value: str) -> bool:
    if not value:
        return False
    return value[0].isalpha() or value[0] in {"[", '"'}
