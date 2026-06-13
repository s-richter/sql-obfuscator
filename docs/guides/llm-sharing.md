# Sharing SQL With an External LLM

This guide explains how to prepare SQL for an external LLM, what the tool checks, what may
still remain visible, and how to restore edited SQL afterward.

## Quick Start

For a privacy-oriented copy that does not need its original literal values restored:

```bash
python obfuscator.py obfuscate script.sql \
  --llm-safe \
  --redaction-mode irreversible \
  --redact-literals \
  --strip-comments
```

If the command succeeds, send only:

- `script.obf/obfuscated.sql`
- `script.obf/llm_instructions.md`

Do not send the entire `script.obf/` folder. It contains `original.sql`, identifier mappings,
and other metadata intended to remain local.

## What The Command Does

The quick-start command combines identifier replacement, redaction, comment removal, and
validation:

| Option | Purpose |
|---|---|
| `obfuscate` | Replaces supported identifiers with generated names |
| `--redaction-mode irreversible` | Uses one-way redaction so original literal values are not stored for restoration |
| `--redact-literals` | Replaces string and numeric values |
| `--strip-comments` | Removes SQL comments |
| `--llm-safe` | Stops with an error when known higher-risk visible content remains |

`--llm-safe` is a validation check, not a redaction preset. Running only:

```bash
python obfuscator.py obfuscate script.sql --llm-safe
```

does not remove comments or literal values. Add the redaction options when the output will
leave your environment.

## What Is Hidden

The normal obfuscation pass replaces:

- table names, including `#temp` and `##global_temp`
- column references
- CTE names
- table aliases
- projection aliases created with `AS`
- column definitions
- insert target column lists

Optional redaction can also remove comments and sanitize literal values.

## What Can Remain Visible

Some SQL text is intentionally not renamed by the normal identifier pass:

- variables such as `@UserId` and `@@ROWCOUNT`
- schema qualifiers such as `dbo` or `sales`
- database or catalog qualifiers
- function invocation names
- SQL keywords
- boolean and `NULL` tokens
- numeric datatype parameters such as `NUMERIC(10,2)`

Some of these values may reveal information about your system. Review generated SQL before
sharing it, even when `--llm-safe` succeeds.

## What `--llm-safe` Checks

`--llm-safe` makes the command stop when a safety check fails. This prevents a failed check
from being mistaken for approved external-sharing output. This stop-on-failure behavior is
sometimes called **fail-closed** behavior.

A **fallback-preserved statement** is SQL copied through without full obfuscation because
the parser could not reliably transform it. Selected procedural T-SQL constructs can use
this path, including some `WAITFOR`, cursor, `WHILE`, and `IF` statements.

The command rejects external-sharing approval when it detects:

| Finding | Why it is blocked |
|---|---|
| A fallback-preserved statement | The parser could not fully transform the statement, so it may still contain original names or values |
| Privacy-audit parse failure | The generated SQL could not be fully checked |
| Local variables such as `@UserId` | The original variable name remains visible |
| User-defined or unknown function names | The function name may reveal system-specific information |
| Custom schema qualifiers such as `sales` | The schema name remains visible |
| Catalog qualifiers | A database or catalog name remains visible |

The audit can also print warnings that do not block approval:

| Finding | Why it is a warning rather than a blocker |
|---|---|
| System variables such as `@@ROWCOUNT` | Usually standard database syntax, but still visible |
| Common schemas such as `dbo`, `sys`, or `information_schema` | Common names, but still visible |

Warnings mean that manual review is recommended before sharing.

## If Validation Fails

When `obfuscate --llm-safe` rejects a script:

- the command returns exit code `1`
- the sibling file such as `script_obfuscated.sql` is not written
- the local workspace is still written so you can inspect the failure

Read these reports first:

- `script.obf/reports/privacy_summary.json`
- `script.obf/reports/llm_workflow_report.json`

Common responses are:

1. Remove, isolate, or rename the visible higher-risk content in a copy of the SQL.
2. Split the script into smaller files so fully transformable SQL can be shared separately.
3. Review the generated SQL manually and decide whether a manual-review workflow is
   acceptable.

The third option is an **expert mode** workflow. It means you deliberately accept larger
edits, more manual review, or content that the tool could not approve automatically.

## Choose A Redaction Mode

| Goal | Recommended mode |
|---|---|
| Send SQL for explanation or edits without restoring original values | `irreversible` |
| Restore original values after LLM edits | `reversible` |
| Keep all literal values because SQL remains local | `none` |

### Irreversible Redaction

```bash
python obfuscator.py obfuscate script.sql \
  --llm-safe \
  --redaction-mode irreversible \
  --redact-literals \
  --strip-comments
```

Strings become `'<REDACTED_STR>'`. Numeric values become `0`. The original values are not
stored in redaction metadata and cannot be restored by `deobfuscate`.

### Reversible Redaction

```bash
python obfuscator.py obfuscate script.sql \
  --llm-safe \
  --redaction-mode reversible \
  --redact-literals \
  --strip-comments
```

Strings and numbers become placeholders such as:

```text
__SQL_OBFUSCATOR_STR_000001__
__SQL_OBFUSCATOR_NUM_000002__
```

The workspace stores the original values locally in `redaction.json`. Keep placeholders
unchanged during LLM edits so `deobfuscate` can restore them.

### Redaction Policies

Literal redaction defaults to `all`.

| Policy | Behavior |
|---|---|
| `all` | Redact string and numeric literals, except numeric datatype parameters |
| `strings-only` | Redact only string literals |
| `sensitive` | Redact literals associated with configured sensitive columns |

Example selective policy:

```bash
python obfuscator.py obfuscate script.sql \
  --llm-safe \
  --redaction-mode irreversible \
  --redact-literals \
  --strip-comments \
  --redaction-policy sensitive \
  --redaction-sensitive-columns email,ssn,token
```

Selective redaction preserves more query detail but increases the amount of visible
information. Review the output before sharing it.

## Ask For Small Edits

The recommended edit workflow asks the LLM to change specific statements instead of
rewriting the entire script. This is a **bounded edit**: the requested change stays inside
known statement IDs and leaves unrelated statements untouched.

Small edits reduce the risk that the LLM changes generated identifiers, aliases,
placeholders, statement order, or table relationships in ways that make restoration
unreliable.

Give the LLM:

- `script.obf/obfuscated.sql`
- `script.obf/llm_instructions.md`

Ask it to return JSON statement replacements. Example:

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

Save the response as `script.obf/llm_edits.json`, then apply it:

```bash
python obfuscator.py apply-llm-edits \
  --workspace script.obf \
  --edits script.obf/llm_edits.json
```

This validates the edit payload and writes:

```text
script.obf/llm_response_obfuscated.sql
```

Untouched statements remain exactly as they appeared in `obfuscated.sql`.

## Validate And Restore

Check the edited SQL without writing restored output:

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

The restored SQL is written to:

```text
script.obf/deobfuscated.sql
```

The validation output may use these terms:

| Term | Meaning |
|---|---|
| unresolved | A generated name or placeholder could not be restored automatically |
| ambiguous | More than one restoration target is possible |
| low-confidence | The tool found a likely match, but structural edits reduced confidence |

Treat these findings as reasons for manual review. Override flags exist for deliberate
manual-review workflows, not as a normal next step.

## Read-Only LLM Tasks

If the LLM only needs to explain or review SQL, you can stop after successful obfuscation.
There is no need to run `apply-llm-edits` or `deobfuscate`.

Examples:

- summarize query behavior
- explain joins or aggregations
- identify likely performance issues
- list questions for a human reviewer

## Larger Rewrites

Some changes are poor fits for automatic restoration:

- introducing new tables or columns
- reorganizing a script across multiple statements
- changing CTE structure substantially
- renaming generated aliases
- removing reversible-redaction placeholders
- rewriting statements that were copied through without full obfuscation

Use a manual-review workflow for these tasks. Keep the original workspace local, inspect the
LLM output carefully, and run `deobfuscate --dry-run` before writing restored SQL.

## Related Documents

- [Command Tutorial](command-tutorial.md)
- [Command Reference](../reference/cli.md)
- [Workspaces and Reports](../reference/workspaces-and-reports.md)
- [Troubleshooting](troubleshooting.md)
