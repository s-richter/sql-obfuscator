# Troubleshooting

Start with the command exit code:

- `0`: the command completed successfully
- `1`: input, validation, integrity, parsing, or runtime checks failed

When a workspace exists, inspect it with:

```bash
python obfuscator.py workspace-info --workspace script.obf
```

## `LLM-safe validation failed`

### Meaning

`obfuscate --llm-safe` or `roundtrip --llm-safe` found content that it could not approve for
the recommended external-sharing workflow.

Common causes:

- a statement was copied without full obfuscation because the parser could not transform it
- local variables such as `@UserId` remain visible
- custom schema names remain visible
- catalog names remain visible
- user-defined or unknown function names remain visible
- the privacy audit could not parse the generated SQL

### What To Do

1. Open `script.obf/reports/privacy_summary.json`.
2. Check `blocking_identifier_classes`, `blockers`, and `identifier_surface`.
3. Open `script.obf/reports/llm_workflow_report.json` for statement and redaction counts.
4. Remove, isolate, or manually review the visible content.
5. Run `obfuscate --llm-safe` again before external sharing.

The workspace is still written locally for diagnosis. Do not share the workspace folder.

## Parser-Fallback Notice

### Symptom

The CLI prints a notice similar to:

```text
Notice: sqlglot used fallback parsing for 1 statement(s) ...
```

### Meaning

Some advanced procedural T-SQL constructs use a compatibility path. A notice alone does not
mean local obfuscation or roundtrip failed.

For external sharing, `--llm-safe` rejects these copied-through statements because the tool
cannot confirm that their contents were fully sanitized.

### What To Do

1. Check the command exit code.
2. For `roundtrip`, inspect `reports/roundtrip_report.json`.
3. For external sharing, isolate or manually review SQL that was copied through without full obfuscation.
4. If behavior appears wrong, reduce the script to the smallest failing statement.

## Unknown Identifiers

### Symptom

Dry-run output contains:

```text
unknown_count > 0
```

### Meaning

Edited SQL contains generated names that are not present in the workspace mapping. An LLM
may have renamed a generated identifier or introduced a new table or column.

### What To Do

1. Compare edited SQL with `obfuscated.sql`.
2. Ask the LLM to preserve generated names.
3. Prefer `apply-llm-edits` so untouched statements remain unchanged.
4. Run `deobfuscate --dry-run` again.
5. Use `--allow-unresolved` only after manual review.

## Ambiguous Identifiers

### Symptom

Dry-run output contains:

```text
ambiguous_count > 0
```

### Meaning

More than one restoration target is possible. This can happen after substantial alias,
scope, or query-structure changes.

### What To Do

1. Reduce the size of the edit.
2. Preserve aliases and statement structure.
3. Prefer structured statement replacements over full-file rewrites.
4. Review any forced output manually.

## Low-Confidence Mappings

### Symptom

Dry-run output contains:

```text
low_confidence_count > 0
```

### Meaning

The tool found a likely restoration match, but structural changes reduced its confidence.

### What To Do

1. Inspect the edited statement.
2. Reduce structural changes where possible.
3. Run `deobfuscate --dry-run` again.
4. Use `--allow-low-confidence` only after manual review.

## Reversible-Redaction Placeholders Are Unresolved

### Symptom

Dry-run output contains:

```text
redaction_unknown_placeholder_count > 0
```

or:

```text
redaction_missing_placeholder_count > 0
```

### Meaning

An LLM edit changed, removed, or invented placeholder values created by reversible
redaction.

### What To Do

1. Compare the edited SQL with `obfuscated.sql`.
2. Restore the exact placeholder text where appropriate.
3. Ask the LLM to preserve placeholders exactly.
4. Run `deobfuscate --dry-run` again.

## Integrity Check Failed

### Symptom

The error mentions a checksum mismatch for a workspace file.

### Meaning

A protected workspace file changed after workspace creation. Protected files include
`original.sql`, `obfuscated.sql`, `mapping.json`, `context.json`, and reversible-redaction
metadata when present.

### What To Do

1. Restore the workspace from a trusted copy, or
2. Re-run `obfuscate` to generate a fresh workspace.

Do not edit checksum metadata to bypass the failure.

## `apply-llm-edits` Failed

### Common Causes

- unknown statement ID
- duplicate statement ID
- replacement SQL contains more than one statement
- replacement SQL cannot be parsed
- stale workspace without the required statement metadata
- attempt to overwrite workspace `obfuscated.sql`

### What To Do

1. Read `script.obf/llm_instructions.md`.
2. Check that the LLM returned the `statement_replacements` JSON format.
3. Confirm each `sql` value contains exactly one obfuscated SQL statement.
4. Re-run `obfuscate` if the workspace was created by an older version.

## Strict `GO` Validation Failed

### Meaning

`--strict-go` found a T-SQL line that begins with `GO` but is not a standalone separator.

Valid:

```sql
SELECT 1;
GO
SELECT 2;
```

Rejected in strict mode:

```sql
GO extra_text
```

### What To Do

Use standalone `GO` lines or omit `--strict-go` when strict validation is unnecessary.

## Translation Failed

### Common Causes

- source SQL cannot be parsed
- generated SQL cannot be emitted or parsed in the target dialect
- conflicting output flags

### What To Do

1. Re-run with `--workspace <dir>`.
2. Inspect `reports/translation_report.json`.
3. Add `--validate` when checking target-dialect parseability.
4. Remove invalid combinations such as `--out` with `--output-dir`.
5. Translate smaller sections when dialect-specific syntax is unsupported.

Translation validation checks whether the generated SQL can be parsed. It does not prove
that the SQL behaves the same way on the target database.

## Related Documents

- [Sharing SQL With an External LLM](llm-sharing.md)
- [Command Reference](../reference/cli.md)
- [Workspaces and Reports](../reference/workspaces-and-reports.md)
