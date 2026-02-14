from __future__ import annotations

from collections.abc import Sequence

from sqlglot.expressions import Expression

from .registry import IdentifierRegistry


def transform_statements(
    statements: Sequence[Expression], *, registry: IdentifierRegistry
) -> list[Expression]:
    """Placeholder transformer. Returns statements unchanged for now."""
    del registry
    return list(statements)
