from __future__ import annotations

import pytest

from sql_obfuscator.errors import WorkspaceError
from sql_obfuscator.llm_edits import apply_llm_statement_replacements, parse_llm_edits_text
from sql_obfuscator.pipeline import obfuscate_sql_with_metadata


def test_parse_llm_edits_accepts_fenced_json_block():
    payload = parse_llm_edits_text(
        """
        ```json
        {
          "schema_version": 1,
          "format": "statement_replacements",
          "edits": []
        }
        ```
        """
    )

    assert payload["schema_version"] == 1
    assert payload["format"] == "statement_replacements"
    assert payload["edits"] == []



def test_apply_llm_edits_with_no_edits_reconstructs_original_obfuscated_sql():
    obfuscated = obfuscate_sql_with_metadata(
        "SELECT UserId FROM Users; SELECT OrderId FROM Orders;",
        seed=7,
        pretty=False,
    )

    output_sql, report = apply_llm_statement_replacements(
        obfuscated_sql=obfuscated.output_sql,
        statement_anchors=obfuscated.context_payload["statement_anchors"],
        batch_count=obfuscated.context_payload["batch_count"],
        dialect=obfuscated.context_payload["dialect"],
        edits_payload={
            "schema_version": 1,
            "format": "statement_replacements",
            "edits": [],
        },
        statement_count=obfuscated.context_payload["statement_count"],
    )

    assert output_sql == obfuscated.output_sql
    assert report["applied_edit_count"] == 0
    assert report["untouched_statement_count"] == 2



def test_apply_llm_edits_replaces_targeted_statement_and_preserves_untouched_statement():
    obfuscated = obfuscate_sql_with_metadata(
        "SELECT UserId FROM Users; SELECT OrderId FROM Orders;",
        seed=7,
        pretty=False,
    )
    anchors = obfuscated.context_payload["statement_anchors"]
    first_anchor = anchors[0]
    second_anchor = anchors[1]

    output_sql, report = apply_llm_statement_replacements(
        obfuscated_sql=obfuscated.output_sql,
        statement_anchors=anchors,
        batch_count=obfuscated.context_payload["batch_count"],
        dialect=obfuscated.context_payload["dialect"],
        edits_payload={
            "schema_version": 1,
            "format": "statement_replacements",
            "edits": [
                {
                    "statement_id": second_anchor["statement_id"],
                    "sql": f"{second_anchor['obfuscated_sql']} WHERE 1 = 1",
                }
            ],
        },
        statement_count=obfuscated.context_payload["statement_count"],
    )

    assert output_sql.startswith(first_anchor["obfuscated_sql"])
    assert f"{second_anchor['obfuscated_sql']} WHERE 1 = 1" in output_sql
    assert report["targeted_statement_ids"] == [second_anchor["statement_id"]]



def test_apply_llm_edits_rejects_unknown_statement_id():
    obfuscated = obfuscate_sql_with_metadata("SELECT UserId FROM Users;", seed=7, pretty=False)

    with pytest.raises(WorkspaceError, match="unknown statement_id"):
        apply_llm_statement_replacements(
            obfuscated_sql=obfuscated.output_sql,
            statement_anchors=obfuscated.context_payload["statement_anchors"],
            batch_count=obfuscated.context_payload["batch_count"],
            dialect=obfuscated.context_payload["dialect"],
            edits_payload={
                "schema_version": 1,
                "format": "statement_replacements",
                "edits": [
                    {
                        "statement_id": "stmt_9999",
                        "sql": "SELECT anything",
                    }
                ],
            },
            statement_count=obfuscated.context_payload["statement_count"],
        )



def test_apply_llm_edits_rejects_multi_statement_sql():
    obfuscated = obfuscate_sql_with_metadata("SELECT UserId FROM Users;", seed=7, pretty=False)
    anchor = obfuscated.context_payload["statement_anchors"][0]

    with pytest.raises(WorkspaceError, match="exactly one"):
        apply_llm_statement_replacements(
            obfuscated_sql=obfuscated.output_sql,
            statement_anchors=obfuscated.context_payload["statement_anchors"],
            batch_count=obfuscated.context_payload["batch_count"],
            dialect=obfuscated.context_payload["dialect"],
            edits_payload={
                "schema_version": 1,
                "format": "statement_replacements",
                "edits": [
                    {
                        "statement_id": anchor["statement_id"],
                        "sql": "SELECT 1; SELECT 2;",
                    }
                ],
            },
            statement_count=obfuscated.context_payload["statement_count"],
        )
