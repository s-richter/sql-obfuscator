from sql_obfuscator.llm_instructions import build_default_llm_instructions
from sql_obfuscator.workspace import (
    build_default_llm_instructions as build_workspace_default_llm_instructions,
)


def test_build_default_llm_instructions_renders_host_neutral_preview():
    instructions = build_default_llm_instructions(
        input_name="sample.sql",
        dialect="tsql",
        statement_anchors=[
            {
                "statement_id": "stmt_0042",
                "batch_index": 2,
                "statement_index": 3,
                "statement_kind": "select",
                "preview": "SELECT ...",
                "fallback_preserved": True,
            }
        ],
    )

    assert "- Original input file: `sample.sql`" in instructions
    assert "- SQL dialect: `tsql`" in instructions
    assert "`stmt_0042`: batch 2, statement 3, kind `select` [fallback-preserved]" in instructions
    assert '"statement_id": "stmt_0042"' in instructions
    assert "Recommended mode: bounded edit" in instructions


def test_workspace_instruction_renderer_remains_compatible():
    kwargs = {
        "input_name": "sample.sql",
        "dialect": "hive",
        "statement_anchors": [
            {
                "statement_id": "stmt_0001",
                "batch_index": 1,
                "statement_index": 1,
                "statement_kind": "select",
            }
        ],
    }

    assert build_workspace_default_llm_instructions(**kwargs) == build_default_llm_instructions(
        **kwargs
    )
