from __future__ import annotations

from dataclasses import dataclass

from sqlglot import exp
from sqlglot.expressions import Expression

from .dialects_base import DialectProfile
from .qualifiers import is_common_schema_qualifier


@dataclass(frozen=True)
class IdentifierOccurrenceContext:
    batch_index: int
    statement_index: int
    scope_id: str
    parent_kind: str
    statement_kind: str
    clause_kind: str
    node_kind: str
    arg_key: str

    def as_registry_kwargs(self) -> dict[str, str | int]:
        return {
            "batch_index": self.batch_index,
            "statement_index": self.statement_index,
            "scope_id": self.scope_id,
            "parent_kind": self.parent_kind,
            "statement_kind": self.statement_kind,
            "clause_kind": self.clause_kind,
            "node_kind": self.node_kind,
            "arg_key": self.arg_key,
        }


@dataclass(frozen=True)
class IdentifierOccurrence:
    node: Expression
    identifier: exp.Identifier
    lexeme: str
    kind: str
    role: str
    context: IdentifierOccurrenceContext


def identifier_name(identifier: exp.Identifier | None) -> str | None:
    if not isinstance(identifier, exp.Identifier):
        return None
    return identifier.name


def identifier_raw(identifier: exp.Identifier | None, *, profile: DialectProfile) -> str | None:
    if not isinstance(identifier, exp.Identifier):
        return None
    if identifier.args.get("quoted"):
        return identifier.sql(dialect=profile.sqlglot_dialect)
    return identifier.name


def node_context(
    node: Expression, *, batch_index: int, statement_index: int
) -> IdentifierOccurrenceContext:
    parent_kind = type(node.parent).__name__.lower() if isinstance(node.parent, Expression) else ""
    node_kind = type(node).__name__.lower()
    arg_key = node.arg_key or ""
    return IdentifierOccurrenceContext(
        batch_index=batch_index,
        statement_index=statement_index,
        scope_id=f"b{batch_index}.s{statement_index}.{node_kind}.{arg_key}",
        parent_kind=parent_kind,
        statement_kind=statement_kind(node),
        clause_kind=clause_kind(node),
        node_kind=node_kind,
        arg_key=arg_key,
    )


def clause_kind(node: Expression) -> str:
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


def statement_kind(node: Expression) -> str:
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


def is_update_alias_target(table: exp.Table) -> bool:
    if not isinstance(table.parent, exp.Update) or table.arg_key != "this":
        return False

    table_name = identifier_name(table.this)
    if not table_name:
        return False

    alias_names = {
        alias.this.name
        for alias in table.parent.find_all(exp.TableAlias)
        if isinstance(alias.this, exp.Identifier)
    }
    return table_name in alias_names


def is_set_option_column(column: exp.Column) -> bool:
    parent = column.parent
    if not isinstance(parent, exp.EQ):
        return False
    set_item = parent.parent
    if not isinstance(set_item, exp.SetItem):
        return False
    return isinstance(set_item.parent, exp.Set)


def table_identifier_occurrence(
    table: exp.Table,
    *,
    profile: DialectProfile,
    batch_index: int,
    statement_index: int,
) -> IdentifierOccurrence | None:
    identifier = table.this
    if not isinstance(identifier, exp.Identifier):
        return None
    context = node_context(table, batch_index=batch_index, statement_index=statement_index)
    if is_update_alias_target(table):
        return IdentifierOccurrence(
            node=table,
            identifier=identifier,
            lexeme=identifier_raw(identifier, profile=profile) or identifier.name,
            kind="alias",
            role="update_target_alias",
            context=context,
        )
    return IdentifierOccurrence(
        node=table,
        identifier=identifier,
        lexeme=profile.table_identifier_raw(identifier),
        kind="table",
        role="table_reference",
        context=context,
    )


def column_identifier_occurrences(
    column: exp.Column,
    *,
    profile: DialectProfile,
    batch_index: int,
    statement_index: int,
) -> tuple[IdentifierOccurrence, ...]:
    if is_set_option_column(column):
        return ()

    context = node_context(column, batch_index=batch_index, statement_index=statement_index)
    occurrences: list[IdentifierOccurrence] = []
    identifier = column.this
    if isinstance(identifier, exp.Identifier):
        occurrences.append(
            IdentifierOccurrence(
                node=column,
                identifier=identifier,
                lexeme=identifier_raw(identifier, profile=profile) or identifier.name,
                kind="column",
                role="column_reference",
                context=context,
            )
        )

    qualifier = column.args.get("table")
    if isinstance(qualifier, exp.Identifier):
        occurrences.append(
            IdentifierOccurrence(
                node=column,
                identifier=qualifier,
                lexeme=identifier_raw(qualifier, profile=profile) or qualifier.name,
                kind="alias",
                role="column_qualifier",
                context=context,
            )
        )
    return tuple(occurrences)


def qualifier_identifier_occurrences(
    node: exp.Table | exp.Column,
    *,
    profile: DialectProfile,
    dialect: str,
    batch_index: int,
    statement_index: int,
) -> tuple[IdentifierOccurrence, ...]:
    context = node_context(node, batch_index=batch_index, statement_index=statement_index)
    occurrences: list[IdentifierOccurrence] = []

    catalog = node.args.get("catalog")
    if isinstance(catalog, exp.Identifier):
        occurrences.append(
            IdentifierOccurrence(
                node=node,
                identifier=catalog,
                lexeme=identifier_raw(catalog, profile=profile) or catalog.name,
                kind="catalog_qualifier",
                role=f"{type(node).__name__.lower()}_catalog_qualifier",
                context=context,
            )
        )

    schema = node.args.get("db")
    if isinstance(schema, exp.Identifier):
        lexeme = identifier_raw(schema, profile=profile) or schema.name
        if not is_common_schema_qualifier(lexeme, dialect=dialect):
            occurrences.append(
                IdentifierOccurrence(
                    node=node,
                    identifier=schema,
                    lexeme=lexeme,
                    kind="schema_qualifier",
                    role=f"{type(node).__name__.lower()}_schema_qualifier",
                    context=context,
                )
            )

    return tuple(occurrences)
