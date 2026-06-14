# Sharing SQL With an External LLM

This guide explains the recommended external-LLM workflow first, then describes lower-level
commands for expert and custom workflows.

## Recommended Workflow

Use the workflow commands for the normal path:

1. `prepare-for-llm` creates the SQL and instructions to send to the LLM.
2. `restore-from-llm` applies structured LLM edits, validates restoration, and writes
   restored SQL only when checks pass.

## Prepare SQL For The LLM

Run:

```bash
python obfuscator.py prepare-for-llm script.sql
```

If the command succeeds, send only:

- `script.obf/obfuscated.sql`
- `script.obf/llm_instructions.md`

Do not send the entire `script.obf/` folder. It contains `original.sql`, identifier mappings,
redaction metadata when reversible redaction is used, and reports intended to remain local.

`prepare-for-llm` applies these defaults:

| Behavior | Meaning |
|---|---|
| Identifier obfuscation | Replaces supported identifiers with generated names. |
| Qualifier obfuscation | Replaces custom schema qualifiers and catalog/database qualifiers on supported references. |
| Reversible redaction | Replaces string and numeric literals with placeholders and stores local restoration metadata. |
| Comment stripping | Removes SQL comments from generated SQL. |
| Fail-closed validation | Exits non-zero when known higher-risk visible content remains. |

By default, `prepare-for-llm` does not write a sibling `script_obfuscated.sql` file and does
not print the SQL body to stdout. It prints a short summary showing which files to send.

### Preparation Options

| Option | Use it when |
|---|---|
| `--workspace <dir>` | You want to choose the workspace folder instead of using `script.obf`. |
| `--dialect <tsql|hive>` | The input SQL is not T-SQL. |
| `--seed <int>` | You need repeatable generated names. |
| `--instruction-template <path>` | You want custom `llm_instructions.md` content. |
| `--irreversible` | Original literal values do not need to be restored later. |
| `--expert-mode` | You intend to manually review output that automatic validation cannot approve. |
| `--print-sql` | You explicitly want the obfuscated SQL printed after the summary. |

### Reversible Redaction

`prepare-for-llm` defaults to reversible redaction because the main workflow restores SQL
after LLM edits.

Strings and numbers become placeholders such as:

```text
__SQL_OBFUSCATOR_STR_000001__
__SQL_OBFUSCATOR_NUM_000002__
```

The workspace stores original literal values locally in `redaction.json`. Ask the LLM to
preserve placeholders exactly.

### Irreversible Redaction

Use one-way redaction when original literal values do not need to be restored:

```bash
python obfuscator.py prepare-for-llm script.sql --irreversible
```

Strings become `'<REDACTED_STR>'`. Numeric values become `0`. The original values are not
stored in redaction metadata and cannot be restored later.

## What Is Hidden

The normal identifier pass replaces:

- table names, including `#temp` and `##global_temp`
- column references
- CTE names
- table aliases
- projection aliases created with `AS`
- column definitions
- insert target column lists

`prepare-for-llm` also replaces custom schema qualifiers and catalog/database qualifiers on
table references, column references, and qualified function calls.

## What Can Remain Visible

Some SQL text is intentionally not renamed:

- variables such as `@UserId` and `@@ROWCOUNT`
- common schema qualifiers such as `dbo`, `sys`, `information_schema`, or Hive `default`
- function invocation names
- SQL keywords
- boolean and `NULL` tokens
- numeric datatype parameters such as `NUMERIC(10,2)`

Some of these values may reveal information about your system. Review generated SQL before
sharing it, even when fail-closed validation succeeds.

## What Fail-Closed Validation Checks

`prepare-for-llm` stops when a safety check fails. This prevents a failed check from being
mistaken for approved external-sharing output.

A **fallback-preserved statement** is SQL copied through without full obfuscation because
the parser could not reliably transform it. Selected procedural T-SQL constructs can use
this path, including some `WAITFOR`, cursor, `WHILE`, and `IF` statements.

The command rejects external-sharing approval when it detects:

| Finding | Why it is blocked |
|---|---|
| A fallback-preserved statement | The parser could not fully transform the statement, so it may still contain original names or values. |
| Privacy-audit parse failure | The generated SQL could not be fully checked. |
| Local variables such as `@UserId` | The original variable name remains visible. |
| User-defined or unknown function names | The function name may reveal system-specific information. |
| Custom schema qualifiers | A schema name remains visible in a position not covered by qualifier obfuscation. |
| Catalog qualifiers | A database or catalog name remains visible in a position not covered by qualifier obfuscation. |

The audit can also print warnings that do not block approval:

| Finding | Why it is a warning rather than a blocker |
|---|---|
| System variables such as `@@ROWCOUNT` | Usually standard database syntax, but still visible. |
| Common schemas such as `dbo`, `sys`, or `information_schema` | Common names, but still visible. |

Warnings mean that manual review is recommended before sharing.

## If Preparation Validation Fails

When `prepare-for-llm` rejects a script:

- the command returns exit code `1`
- the local workspace is still written so you can inspect the failure
- no sibling `script_obfuscated.sql` file is written by the workflow command

Read these reports first:

- `script.obf/reports/privacy_summary.json`
- `script.obf/reports/llm_workflow_report.json`

Common responses are:

1. Remove, isolate, or rename the visible higher-risk content in a copy of the SQL.
2. Split the script into smaller files so fully transformable SQL can be shared separately.
3. Review the generated SQL manually and decide whether a manual-review workflow is
   acceptable.

Use `prepare-for-llm --expert-mode` only when you intend to review the generated SQL and
reports before sharing.

## Ask For Small Edits

The recommended edit workflow asks the LLM to change specific statements instead of
rewriting the entire script. This is a **bounded edit**: the requested change stays inside
known statement IDs and leaves unrelated statements untouched.

Send the LLM these two files:

- `script.obf/obfuscated.sql`
- `script.obf/llm_instructions.md`

`llm_instructions.md` contains the workspace-specific statement IDs and tells the LLM to
return JSON statement replacements. Add your task request alongside those instructions, such
as "change `stmt_0002` so it filters out inactive rows" or "review this query and return no
edits if no change is needed."

The expected response shape is:

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

The statement IDs and generated names above are illustrative. The LLM should use the exact
IDs and generated names from the files you sent.

The tool does not call the LLM or save the LLM response automatically. After the LLM returns
JSON, save that response locally as:

```text
script.obf/llm_edits.json
```

## Restore Structured LLM Edits

Run:

```bash
python obfuscator.py restore-from-llm \
  --workspace script.obf \
  --edits script.obf/llm_edits.json
```

This command:

- validates the edit JSON
- writes `script.obf/llm_response_obfuscated.sql`
- validates whether original names and reversible-redaction placeholders can be restored
- writes `script.obf/deobfuscated.sql` only when validation passes

On success, it prints artifact paths and validation status, not the restored SQL body.

### Restoration Options

| Option | Use it when |
|---|---|
| `--out <path>` | You want the final restored SQL written to a specific path. |
| `--dry-run` | You want to validate edits and restoration safety without writing workflow outputs. |
| `--allow-unresolved` | You deliberately accept unresolved or ambiguous names after manual review. |
| `--allow-low-confidence` | You deliberately accept low-confidence restoration matches after manual review. |

Use override flags only after manual review.

## Read-Only LLM Tasks

If the LLM only needs to explain or review SQL, stop after successful `prepare-for-llm`.
There is no need to run `restore-from-llm`, `apply-llm-edits`, or `deobfuscate`.

Examples:

- summarize query behavior
- explain joins or aggregations
- identify likely performance issues
- list questions for a human reviewer

## Lower-Level And Expert Workflows

The sections below are for custom or manual-review workflows. Use them when the workflow
commands are too opinionated for the task.

## Custom Preparation With `obfuscate`

Use lower-level `obfuscate` when you need custom redaction policy, sibling output files,
stdout behavior, or other fine-grained output controls.

The workflow-command equivalent must be assembled explicitly:

```bash
python obfuscator.py obfuscate script.sql \
  --llm-safe \
  --obfuscate-qualifiers \
  --redaction-mode reversible \
  --redact-literals \
  --strip-comments
```

Use irreversible redaction with lower-level `obfuscate`:

```bash
python obfuscator.py obfuscate script.sql \
  --llm-safe \
  --obfuscate-qualifiers \
  --redaction-mode irreversible \
  --redact-literals \
  --strip-comments
```

### Custom Redaction Policies

Redaction policies are available only through lower-level `obfuscate`.

| Policy | Behavior |
|---|---|
| `all` | Redact string and numeric literals, except numeric datatype parameters. |
| `strings-only` | Redact only string literals. |
| `sensitive` | Redact literals associated with configured sensitive columns. |

Example selective policy:

```bash
python obfuscator.py obfuscate script.sql \
  --llm-safe \
  --obfuscate-qualifiers \
  --redaction-mode irreversible \
  --redact-literals \
  --strip-comments \
  --redaction-policy sensitive \
  --redaction-sensitive-columns email,ssn,token
```

Selective redaction preserves more query detail but increases the amount of visible
information. Review the output before sharing it.

## Custom Restoration With Lower-Level Commands

Use lower-level restoration commands when you want to inspect intermediate steps or when you
have a full edited obfuscated SQL file instead of structured edit JSON.

Apply structured edits without restoring yet:

```bash
python obfuscator.py apply-llm-edits \
  --workspace script.obf \
  --edits script.obf/llm_edits.json
```

This writes:

```text
script.obf/llm_response_obfuscated.sql
```

Check a full edited obfuscated SQL file without writing restored output:

```bash
python obfuscator.py deobfuscate \
  --workspace script.obf \
  --input script.obf/llm_response_obfuscated.sql \
  --dry-run
```

Then write restored SQL only when validation passes:

```bash
python obfuscator.py validate-before-write \
  --workspace script.obf \
  --input script.obf/llm_response_obfuscated.sql
```

The validation output may use these terms:

| Term | Meaning |
|---|---|
| unresolved | A generated name or placeholder could not be restored automatically. |
| ambiguous | More than one restoration target is possible. |
| low-confidence | The tool found a likely match, but structural edits reduced confidence. |

Treat these findings as reasons for manual review.

## Larger Rewrites

Some changes are poor fits for automatic restoration:

- introducing new tables or columns
- reorganizing a script across multiple statements
- changing CTE structure substantially
- renaming generated aliases
- removing reversible-redaction placeholders
- rewriting statements that were copied through without full obfuscation

Use a manual-review workflow for these tasks. Keep the original workspace local, inspect the
LLM output carefully, and run `restore-from-llm --dry-run` for structured edit JSON or
`deobfuscate --dry-run` for a full edited SQL file before writing restored SQL.

## Related Documents

- [Command Tutorial](command-tutorial.md)
- [Command Reference](../reference/cli.md)
- [Workspaces and Reports](../reference/workspaces-and-reports.md)
- [Troubleshooting](troubleshooting.md)
