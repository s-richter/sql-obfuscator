# SQL Obfuscator Command Tutorial

This cookbook shows common workflows with short examples. Start with the section matching
your immediate goal, then follow links to the detailed reference only when needed.

## Choose A Task

| Goal | Section |
|---|---|
| Replace identifiers locally | [1. Basic obfuscation](#1-basic-obfuscation) |
| Generate repeatable output | [2. Repeatable output and custom folders](#2-repeatable-output-and-custom-folders) |
| Send SQL to an external LLM | [3. Prepare SQL for an external LLM](#3-prepare-sql-for-an-external-llm) |
| Restore structured LLM edits | [4. Restore from LLM edits](#4-restore-from-llm-edits) |
| Use lower-level LLM commands | [5. Customize the LLM workflow](#5-customize-the-llm-workflow) |
| Validate and restore full edited SQL | [6. Validate and restore a full edited SQL file](#6-validate-and-restore-a-full-edited-sql-file) |
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

For external-sharing checks, qualifier obfuscation, redaction choices, structured edits,
and manual-review workflows, see [the LLM-sharing guide](llm-sharing.md).

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

## 3. Prepare SQL For An External LLM

Suppose you want an external LLM to explain a query, suggest performance questions, or make
small bounded edits.

Run:

```bash
python obfuscator.py prepare-for-llm sample.sql
```

This command:

- replaces supported identifiers
- obfuscates custom schema qualifiers and catalog/database qualifiers on table references, column references, and qualified function calls
- removes comments
- replaces string and numeric values with reversible placeholders
- stops with an error if known higher-risk visible content remains
- avoids writing a sibling `sample_obfuscated.sql` file

The command stops when a safety check fails. This prevents a failed check from being mistaken
for approved external-sharing output. This stop-on-failure behavior is fail-closed
validation.

If the command succeeds, send only:

```text
sample.obf/obfuscated.sql
sample.obf/llm_instructions.md
```

Do not send the entire workspace. It contains the original SQL and restoration metadata.

Use one-way redaction when original literal values do not need to be restored:

```bash
python obfuscator.py prepare-for-llm sample.sql --irreversible
```

For the exact safety checks and limitations, read
[Sharing SQL With an External LLM](llm-sharing.md).

## 4. Restore From LLM Edits

Ask the LLM to return the JSON statement replacements described in
`sample.obf/llm_instructions.md`. Save the response as `sample.obf/llm_edits.json`.

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

Apply, validate, and restore in one command:

```bash
python obfuscator.py restore-from-llm \
  --workspace sample.obf \
  --edits sample.obf/llm_edits.json
```

Result:

```text
sample.obf/llm_response_obfuscated.sql
sample.obf/deobfuscated.sql
```

`restore-from-llm` writes restored SQL only when validation passes. Check the workflow
without writing derived outputs:

```bash
python obfuscator.py restore-from-llm \
  --workspace sample.obf \
  --edits sample.obf/llm_edits.json \
  --dry-run
```

## 5. Customize The LLM Workflow

Use lower-level commands when you need to inspect or customize each step.

Prepare SQL with a custom redaction policy:

```bash
python obfuscator.py obfuscate sample.sql \
  --llm-safe \
  --obfuscate-qualifiers \
  --redaction-mode reversible \
  --redact-literals \
  --strip-comments \
  --redaction-policy strings-only
```

Apply structured edits without restoring yet:

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

## 6. Validate And Restore A Full Edited SQL File

`restore-from-llm` expects structured edit JSON. If you have a full edited obfuscated SQL
file instead, use the lower-level restoration commands.

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
- lists available generated files and reports
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
