from __future__ import annotations

from sqlglot import parse
from sqlglot.errors import ParseError

from .errors import ParseScriptError
from .go_batches import join_batches, split_batches
from .registry import IdentifierRegistry
from .transformer import transform_statements


def _process_batch(batch_sql: str, *, dialect: str, registry: IdentifierRegistry) -> str:
    if not batch_sql.strip():
        return batch_sql

    try:
        statements = parse(batch_sql, dialect=dialect)
    except ParseError as exc:
        raise ParseScriptError(str(exc)) from exc

    transformed = transform_statements(statements, registry=registry)
    return ";\n".join(stmt.sql(dialect=dialect) for stmt in transformed)


def obfuscate_sql(
    script: str,
    *,
    dialect: str = "tsql",
    seed: int | None = None,
    strict_go: bool = False,
) -> str:
    del strict_go  # reserved for future strict GO edge-case handling
    registry = IdentifierRegistry(seed=seed)
    batches = split_batches(script)
    transformed_batches = [
        _process_batch(batch, dialect=dialect, registry=registry) for batch in batches
    ]
    return join_batches(transformed_batches)
