from __future__ import annotations

from typing import Any

from .llm_edits import llm_edits_example_json


def build_default_llm_instructions(
    *,
    input_name: str,
    dialect: str,
    statement_anchors: list[dict[str, Any]] | None = None,
) -> str:
    return (
        "# LLM Instructions for Obfuscated SQL\n\n"
        "You are editing an obfuscated SQL script. The output will be de-obfuscated afterward.\n\n"
        "## Input Context\n"
        f"- Original input file: `{input_name}`\n"
        f"- SQL dialect: `{dialect}`\n\n"
        + _statement_anchor_instruction_lines(statement_anchors)
        + _statement_replacement_instruction_lines(statement_anchors)
        + "## Workflow Modes\n"
        "- Recommended mode: bounded edit. Preserve obfuscated identifiers and overall statement structure.\n"
        "- Expert mode: larger rewrites are allowed only when explicitly required and can trigger unresolved, ambiguous, or low-confidence restore results.\n\n"
        "## Bounded-Edit Requirements\n"
        "1. Keep obfuscated identifiers unchanged whenever possible.\n"
        "2. Do not invent new table or column names unless absolutely required.\n"
        "3. Keep alias structure stable and avoid renaming aliases.\n"
        "4. Do not rewrite JOIN graph, CTE hierarchy, or table lineage unless required.\n"
        "5. Preserve placeholder literals exactly when present (for reversible redaction).\n"
        "6. Prefer local predicate or projection optimizations over large structural rewrites.\n"
        "7. Preserve SQL semantics unless explicitly asked to change behavior.\n\n"
        "## Expert Mode Guardrails\n"
        "- Edit the smallest region that solves the task.\n"
        "- Avoid reordering statements unless required.\n"
        "- Minimize new identifiers and keep any new identifiers syntactically valid for the dialect.\n"
        "- If you must introduce larger rewrites, keep untouched statements as close to the input as possible.\n"
        "- If exact identifier or placeholder preservation is not possible, say so in a short SQL comment.\n"
    )


def _statement_anchor_instruction_lines(statement_anchors: list[dict[str, Any]] | None) -> str:
    anchors = statement_anchors or []
    if not anchors:
        return ""
    lines = [
        "## Statement Anchors",
        "Use these IDs when referring to specific statements or planning constrained edits.",
    ]
    for anchor in anchors:
        statement_id = anchor.get("statement_id")
        if not isinstance(statement_id, str):
            continue
        batch_index = anchor.get("batch_index")
        statement_index = anchor.get("statement_index")
        statement_kind = anchor.get("statement_kind")
        preview = anchor.get("preview")
        fallback_preserved = anchor.get("fallback_preserved")
        detail = (
            f"- `{statement_id}`: batch {batch_index}, statement {statement_index}, kind `{statement_kind}`"
        )
        if fallback_preserved:
            detail += " [fallback-preserved]"
        if isinstance(preview, str) and preview:
            detail += f" - `{preview}`"
        lines.append(detail)
    return "\n".join(lines) + "\n\n"


def _statement_replacement_instruction_lines(statement_anchors: list[dict[str, Any]] | None) -> str:
    example_statement_id = "stmt_0001"
    for anchor in statement_anchors or []:
        statement_id = anchor.get("statement_id")
        if isinstance(statement_id, str) and statement_id:
            example_statement_id = statement_id
            break
    example_json = llm_edits_example_json(statement_id=example_statement_id)
    return (
        "## Preferred Response Format\n"
        "For production and bounded-edit workflows, return JSON statement replacements instead of a full rewritten script.\n\n"
        "```json\n"
        f"{example_json}\n"
        "```\n\n"
        "- Include only changed statements in `edits`.\n"
        "- Each `sql` value must contain exactly one replacement statement.\n"
        "- Omit untouched statements so `apply-llm-edits` can preserve them exactly.\n"
        "- Raw JSON or a fenced ```json``` block are both accepted.\n\n"
    )
