from __future__ import annotations

from collections.abc import Sequence

from sqlglot import exp
from sqlglot.expressions import Expression

from .registry import IdentifierRegistry


def _identifier_name(identifier: exp.Identifier | None) -> str | None:
    if not isinstance(identifier, exp.Identifier):
        return None
    return identifier.name


def _raw_table_name(identifier: exp.Identifier) -> str:
    prefix = ""
    if identifier.args.get("global_"):
        prefix = "##"
    elif identifier.args.get("temporary"):
        prefix = "#"
    return f"{prefix}{identifier.name}"


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


def _rename_table(table: exp.Table, registry: IdentifierRegistry) -> exp.Table:
    identifier = table.this
    if not isinstance(identifier, exp.Identifier):
        return table

    if _is_update_alias_target(table):
        # UPDATE alias target should follow alias obfuscation, not table-name obfuscation.
        identifier.set("this", registry.get_or_create(identifier.name))
        return table

    renamed = registry.get_or_create(_raw_table_name(identifier))
    identifier.set("this", renamed.lstrip("#"))
    return table


def _rename_column(column: exp.Column, registry: IdentifierRegistry) -> exp.Column:
    identifier = column.this
    if isinstance(identifier, exp.Identifier):
        identifier.set("this", registry.get_or_create(identifier.name))

    table_identifier = column.args.get("table")
    if isinstance(table_identifier, exp.Identifier):
        table_identifier.set("this", registry.get_or_create(table_identifier.name))

    return column


def _rename_cte(cte: exp.CTE, registry: IdentifierRegistry) -> exp.CTE:
    alias = cte.args.get("alias")
    if not isinstance(alias, exp.TableAlias) or not isinstance(alias.this, exp.Identifier):
        return cte
    alias.this.set("this", registry.get_or_create(alias.this.name))
    return cte


def _rename_table_alias(table_alias: exp.TableAlias, registry: IdentifierRegistry) -> exp.TableAlias:
    # CTE declaration alias is handled in _rename_cte.
    if isinstance(table_alias.parent, exp.CTE):
        return table_alias

    alias_identifier = table_alias.this
    if isinstance(alias_identifier, exp.Identifier):
        alias_identifier.set("this", registry.get_or_create(alias_identifier.name))

    for identifier in table_alias.args.get("columns") or []:
        if isinstance(identifier, exp.Identifier):
            identifier.set("this", registry.get_or_create(identifier.name))

    return table_alias


def _rename_expression_alias(alias: exp.Alias, registry: IdentifierRegistry) -> exp.Alias:
    alias_identifier = alias.args.get("alias")
    if isinstance(alias_identifier, exp.Identifier):
        alias_identifier.set("this", registry.get_or_create(alias_identifier.name))
    return alias


def _rename_column_def(column_def: exp.ColumnDef, registry: IdentifierRegistry) -> exp.ColumnDef:
    identifier = column_def.this
    if not isinstance(identifier, exp.Identifier):
        return column_def
    identifier.set("this", registry.get_or_create(identifier.name))
    return column_def


def _rename_insert_column_list(schema: exp.Schema, registry: IdentifierRegistry) -> exp.Schema:
    if not isinstance(schema.parent, exp.Insert) or schema.arg_key != "this":
        return schema
    for identifier in schema.expressions:
        if isinstance(identifier, exp.Identifier):
            identifier.set("this", registry.get_or_create(identifier.name))
    return schema


def transform_statements(
    statements: Sequence[Expression], *, registry: IdentifierRegistry
) -> list[Expression]:
    transformed: list[Expression] = []

    def _transform(node: Expression) -> Expression:
        if isinstance(node, exp.Table):
            return _rename_table(node, registry)
        if isinstance(node, exp.Column):
            return _rename_column(node, registry)
        if isinstance(node, exp.CTE):
            return _rename_cte(node, registry)
        if isinstance(node, exp.TableAlias):
            return _rename_table_alias(node, registry)
        if isinstance(node, exp.Alias):
            return _rename_expression_alias(node, registry)
        if isinstance(node, exp.ColumnDef):
            return _rename_column_def(node, registry)
        if isinstance(node, exp.Schema):
            return _rename_insert_column_list(node, registry)
        return node

    for statement in statements:
        transformed.append(statement.transform(_transform, copy=True))

    return transformed
