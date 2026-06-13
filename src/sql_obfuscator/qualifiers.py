from __future__ import annotations

COMMON_SAFE_SCHEMAS_BY_DIALECT = {
    "tsql": {"dbo", "sys", "information_schema"},
    "hive": {"default", "information_schema"},
}


def is_common_schema_qualifier(value: str, *, dialect: str) -> bool:
    normalized = value.strip().strip("[]`\"").lower()
    if not normalized:
        return False
    return normalized in COMMON_SAFE_SCHEMAS_BY_DIALECT.get(dialect.lower(), set())
