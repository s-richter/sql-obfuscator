from sqlglot import exp

from sql_obfuscator.dialects_factory import get_dialect_profile
from sql_obfuscator.identifier_occurrences import (
    column_identifier_occurrences,
    table_identifier_occurrence,
)
from sql_obfuscator.sqlglot_compat import parse_sql


def test_table_and_column_identifier_occurrences_describe_shared_context():
    profile = get_dialect_profile("tsql")
    statement = parse_sql(
        "SELECT u.UserId FROM Users u WHERE u.UserId > 0",
        dialect="tsql",
    )[0]
    table = next(statement.find_all(exp.Table))
    column = next(statement.find_all(exp.Column))

    table_occurrence = table_identifier_occurrence(
        table,
        profile=profile,
        batch_index=2,
        statement_index=3,
    )
    column_occurrences = column_identifier_occurrences(
        column,
        profile=profile,
        batch_index=2,
        statement_index=3,
    )

    assert table_occurrence is not None
    assert table_occurrence.lexeme == "Users"
    assert table_occurrence.kind == "table"
    assert table_occurrence.role == "table_reference"
    assert table_occurrence.context.batch_index == 2
    assert table_occurrence.context.statement_index == 3
    assert table_occurrence.context.node_kind == "table"
    assert table_occurrence.context.statement_kind == "select"

    assert [(occurrence.kind, occurrence.role, occurrence.lexeme) for occurrence in column_occurrences] == [
        ("column", "column_reference", "UserId"),
        ("alias", "column_qualifier", "u"),
    ]
    assert column_occurrences[0].context.scope_id.startswith("b2.s3.column.")
    assert column_occurrences[1].context == column_occurrences[0].context


def test_update_alias_target_occurrence_is_classified_as_alias():
    profile = get_dialect_profile("tsql")
    statement = parse_sql(
        "UPDATE u SET u.UserId = 1 FROM Users u",
        dialect="tsql",
    )[0]
    update_target = next(statement.find_all(exp.Table))

    occurrence = table_identifier_occurrence(
        update_target,
        profile=profile,
        batch_index=1,
        statement_index=1,
    )

    assert occurrence is not None
    assert occurrence.lexeme == "u"
    assert occurrence.kind == "alias"
    assert occurrence.role == "update_target_alias"
    assert occurrence.context.statement_kind == "update"
