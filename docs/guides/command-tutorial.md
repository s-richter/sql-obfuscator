# SQL Obfuscator Command Tutorial

This cookbook shows common workflows with short examples. Start with the section matching
your immediate goal, then follow links to the detailed reference only when needed.

## Choose A Task

| Goal | Section |
|---|---|
| Replace identifiers locally | [1. Basic obfuscation](#1-basic-obfuscation) |
| Generate repeatable output | [2. Repeatable output and custom folders](#2-repeatable-output-and-custom-folders) |
| Send SQL to an external LLM for explanation | [3. Share SQL for a read-only LLM task](#3-share-sql-for-a-read-only-llm-task) |
| Send SQL to an LLM and restore edited values later | [4. Use reversible literal redaction](#4-use-reversible-literal-redaction) |
| Apply targeted LLM edits | [5. Apply structured LLM edits](#5-apply-structured-llm-edits) |
| Validate and restore edited SQL | [6. Validate and restore](#6-validate-and-restore) |
| Verify obfuscation on a script | [7. Run a roundtrip check](#7-run-a-roundtrip-check) |
| Translate T-SQL and Hive | [8. Translate SQL](#8-translate-sql) |
| Inspect generated files | [9. Inspect a workspace](#9-inspect-a-workspace) |
| Use stdin or control output paths | [10. Use stdin and output options](#10-use-stdin-and-output-options) |
| Validate T-SQL `GO` separators | [11. Check `GO` separators](#11-check-go-separators) |

Detailed documentation:

- [Sharing SQL With an External LLM](llm-sharing.md)
- [Command Reference](../reference/cli.md)
- [Workspaces and Reports](../reference/workspaces-and-reports.md)
- [Troubleshooting](troubleshooting.md)

## A Few Terms

| Term | Meaning |
|---|---|
| workspace | A local run folder such as `sample.obf/`. It stores generated SQL and restoration metadata. |
| obfuscated SQL | SQL with generated names in place of supported original identifiers. |
| redaction | Sanitizing literal values or removing comments. Identifier replacement and literal redaction are separate features. |
| statement replacement | A JSON edit that asks the tool to replace one known SQL statement instead of accepting a full rewritten file. |
| dry run | A validation pass that prints diagnostics without writing restored SQL. |

For external-sharing terminology such as `--llm-safe`, fail-closed behavior, bounded edits,
and expert mode, see [the LLM-sharing guide](llm-sharing.md).

## 1. Basic Obfuscation

Input file `sample.sql`:

```sql
SELECT customer_id, email
FROM customers
WHERE status = 'active';
```

Run:

```bash
python obfuscator.py obfuscate sample.sql
```

Result:

- `sample_obfuscated.sql` is written.
- `sample.obf/` is created.
- Supported identifier names are replaced.
- Literal values remain visible because redaction was not requested.

This baseline command is suitable for local use. Do not assume the output is ready to send
outside your environment.

## 2. Repeatable Output And Custom Folders

Use `--seed` when tests, reviews, or repeated runs need stable generated names:

```bash
python obfuscator.py obfuscate sample.sql --seed 42
```

Use `--workspace` to keep run metadata in a chosen folder:

```bash
python obfuscator.py obfuscate sample.sql --workspace runs/review_01.obf
```

Use `--output-dir` to place generated SQL in a chosen folder:

```bash
python obfuscator.py obfuscate sample.sql --output-dir artifacts/sql
```

The workspace and generated SQL file serve different purposes. The generated SQL file is
the transformed output. The workspace contains local restoration metadata and reports.

## 3. Share SQL For A Read-Only LLM Task

Suppose you want an external LLM to explain a query or suggest performance questions without
editing the script.

Run:

```bash
python obfuscator.py obfuscate sample.sql \
  --llm-safe \
  --redaction-mode irreversible \
  --redact-literals \
  --strip-comments
```

This command:

- replaces supported identifiers
- removes comments
- replaces string and numeric values
- stops with an error if known higher-risk visible content remains

The stop-on-risk behavior is sometimes called **fail-closed** behavior. It prevents a failed
safety check from being mistaken for approved external-sharing output.

If the command succeeds, send only:

```text
sample.obf/obfuscated.sql
sample.obf/llm_instructions.md
```

Do not send the entire workspace. It contains the original SQL and restoration metadata.

For the exact safety checks and limitations, read
[Sharing SQL With an External LLM](llm-sharing.md).

## 4. Use Reversible Literal Redaction

Use reversible redaction when the LLM will edit SQL and the original literal values must be
restored afterward.

Input file `sample.sql`:

```sql
SELECT account_id
FROM payments
WHERE card_last4 = '1234'
  AND amount > 250.00;
```

Run:

```bash
python obfuscator.py obfuscate sample.sql \
  --llm-safe \
  --redaction-mode reversible \
  --redact-literals \
  --strip-comments
```

Literal values become placeholders similar to:

```text
__SQL_OBFUSCATOR_STR_000001__
__SQL_OBFUSCATOR_NUM_000002__
```

The workspace stores the original values locally in `redaction.json`. Ask the LLM to preserve
the placeholders exactly.

Use irreversible redaction instead when original values do not need to be restored.

## 5. Apply Structured LLM Edits

For edited SQL, ask the LLM to return JSON statement replacements instead of a complete
rewritten script. Generated `llm_instructions.md` describes the expected format and available
statement IDs.

Example `sample.obf/llm_edits.json`:

```json
{
  "schema_version": 1,
  "format": "statement_replacements",
  "edits": [
    {
      "statement_id": "stmt_0002",
      "sql": "SELECT generated_column FROM generated_table WHERE generated_column > 10"
    }
  ]
}
```

The generated names above are illustrative. Use the exact names from your
`obfuscated.sql`.

Apply the edits:

```bash
python obfuscator.py apply-llm-edits \
  --workspace sample.obf \
  --edits sample.obf/llm_edits.json
```

Result:

```text
sample.obf/llm_response_obfuscated.sql
```

`apply-llm-edits` checks that:

- each statement ID exists
- no statement is edited twice
- each replacement contains exactly one statement
- replacement SQL can be parsed

Untouched statements are copied exactly from `obfuscated.sql`. This makes restoration more
reliable than accepting a full-file rewrite.

Validate an edit payload without writing output:

```bash
python obfuscator.py apply-llm-edits \
  --workspace sample.obf \
  --edits sample.obf/llm_edits.json \
  --dry-run
```

## 6. Validate And Restore

First run a dry check:

```bash
python obfuscator.py deobfuscate \
  --workspace sample.obf \
  --input sample.obf/llm_response_obfuscated.sql \
  --dry-run
```

This prints diagnostics without writing restored SQL.

Then write output only when restoration checks pass:

```bash
python obfuscator.py validate-before-write \
  --workspace sample.obf \
  --input sample.obf/llm_response_obfuscated.sql
```

Result:

```text
sample.obf/deobfuscated.sql
```

Validation may report:

| Finding | Meaning |
|---|---|
| unknown | A generated name or placeholder is not recognized. |
| ambiguous | More than one restoration target is possible. |
| low-confidence | A likely match exists, but structural edits reduced confidence. |

See [Troubleshooting](troubleshooting.md) before considering override flags.

## 7. Run A Roundtrip Check

Use `roundtrip` to verify that a script can be obfuscated and restored without an intervening
edit:

```bash
python obfuscator.py roundtrip sample.sql --diff-report
```

The workspace includes:

- restored SQL
- a roundtrip report
- normalized original and restored SQL
- normalized diff output
- a raw diff report when `--diff-report` is present

Formatting or comments may change during SQL regeneration. The normalized comparison helps
separate formatting changes from meaningful SQL changes.

## 8. Translate SQL

Translate T-SQL to Hive:

```bash
python obfuscator.py translate \
  --input sample.sql \
  --source-dialect tsql \
  --target-dialect hive \
  --validate
```

`--validate` parses generated SQL using the target dialect. It catches parse failures but
does not prove identical runtime behavior.

Translate smaller sections when dialect-specific syntax is not supported.

## 9. Inspect A Workspace

```bash
python obfuscator.py workspace-info --workspace sample.obf
```

This command:

- validates protected workspace files
- prints run settings and counts
- lists available artifacts and reports
- shows external-sharing privacy flags when present

Read [Workspaces and Reports](../reference/workspaces-and-reports.md) for the complete file
layout.

## 10. Use Stdin And Output Options

Read SQL from stdin in PowerShell:

```powershell
Get-Content sample.sql | python obfuscator.py obfuscate -
```

Read SQL from stdin in a POSIX shell:

```bash
cat sample.sql | python obfuscator.py obfuscate -
```

Print SQL without writing the sibling generated SQL file:

```bash
python obfuscator.py obfuscate sample.sql --stdout-only
```

The workspace is still created.

Write generated SQL into a chosen folder:

```bash
python obfuscator.py obfuscate sample.sql --output-dir artifacts/sql
```

For translation output combinations, see [the command reference](../reference/cli.md#output-rules).

## 11. Check `GO` Separators

Use standalone `GO` lines in T-SQL:

```sql
SELECT 1;
GO
SELECT 2;
```

Validate them with:

```bash
python obfuscator.py obfuscate sample.sql --strict-go
```

Strict mode rejects lines such as:

```sql
GO extra_text
```

## Next Steps

- Use [the command reference](../reference/cli.md) for all flags.
- Use [the LLM-sharing guide](llm-sharing.md) before sending SQL externally.
- Use [the troubleshooting guide](troubleshooting.md) when a command fails.
