# SQL Identifier Obfuscator

Python CLI tool for obfuscating SQL identifiers (table names, column names, CTE names, aliases, temp tables) in SQL scripts across supported dialects (`tsql`, `hive`) using an AST-based pipeline.

Start here for a scenario-based walkthrough of commands, flags, and expected outputs:

- [Command Tutorial](docs/COMMAND_TUTORIAL.md)

**NOTE**: the code and the documentation in this repository was largely written by **GPT-5.3-Codex Medium**.

## What It Does

- Obfuscates identifier names while preserving SQL syntax.
- Supports deterministic output with seeds.
- Handles multi-batch scripts separated by standalone `GO`.
- Supports SQL translation between supported dialects (`tsql`, `hive`).
- Creates a workspace folder per script with mapping/context artifacts for de-obfuscation workflows.
- Supports LLM workflows: obfuscate -> send to LLM -> de-obfuscate edited output.

## Installation

```bash
pip install -e .
```

Installed CLI command:

```bash
sql-obfuscator --help
```

For development:

```bash
pip install -e .[dev]
```

Optional fallback (runtime dependency only):

```bash
pip install -r requirements.txt
```

## Cheat Sheet

```bash
# Obfuscate (default workspace: script.obf)
python obfuscator.py obfuscate script.sql

# Obfuscate from stdin (workspace defaults to stdin.obf)
cat script.sql | python obfuscator.py obfuscate -

# Obfuscate from file but skip sibling output file write
python obfuscator.py obfuscate script.sql --stdout-only

# Obfuscate deterministically
python obfuscator.py obfuscate script.sql --seed 42

# Obfuscate with custom workspace
python obfuscator.py obfuscate script.sql --workspace my_run.obf

# Obfuscate with irreversible literal/comment redaction for LLM sharing
python obfuscator.py obfuscate script.sql --redaction-mode irreversible --redact-literals --strip-comments

# Validate LLM-edited obfuscated SQL without writing outputs
python obfuscator.py deobfuscate --workspace script.obf --input script.obf/llm_response_obfuscated.sql --dry-run

# De-obfuscate and write restored SQL
python obfuscator.py deobfuscate --workspace script.obf --input script.obf/llm_response_obfuscated.sql

# Validate first, then write only if checks pass
python obfuscator.py validate-before-write --workspace script.obf --input script.obf/llm_response_obfuscated.sql

# One-command verification loop
python obfuscator.py roundtrip script.sql --diff-report

# Translate SQL between dialects
python obfuscator.py translate --input script.sql --source-dialect tsql --target-dialect hive --validate

# Translate from file and print translated SQL only
python obfuscator.py translate --input script.sql --source-dialect tsql --target-dialect hive --stdout-only

# Translate from stdin to stdout
cat script.sql | python obfuscator.py translate --input - --source-dialect tsql --target-dialect hive

# Check workspace health/status (includes integrity check)
python obfuscator.py workspace-info --workspace script.obf
```

## Core Commands

- `obfuscate`: Obfuscate SQL and create workspace artifacts.
- `deobfuscate`: Reverse obfuscation using workspace mapping/context.
- `validate-before-write`: Validate de-obfuscation safety and write output only when checks pass.
- `roundtrip`: Obfuscate and immediately de-obfuscate for verification.
- `translate`: Translate SQL between supported dialects with optional validation/reporting.
- `workspace-info`: Show workspace artifact/report status and integrity info.

Subcommand-only CLI:

```bash
python obfuscator.py obfuscate script.sql
```

## Obfuscation Behavior

### Renamed

- Table names (including `#temp` and `##global_temp`)
- Column references
- CTE names
- Table aliases
- Projection aliases (`AS ...`)
- Column definitions
- Insert target column lists

### Not Renamed

- SQL keywords
- String/numeric literals
- Variables (`@...`)
- Function invocation names
- Schema qualifiers (for example `dbo`)

## Redaction Behavior

Redaction is optional and controlled by:

- `--redact-literals`
- `--strip-comments`
- `--redaction-mode <none|irreversible|reversible>`

Modes:

- `none`: default behavior; no literal/comment redaction.
- `irreversible`: literals/comments are sanitized for LLM sharing and original values are not recoverable from redaction metadata.
- `reversible`: literals are replaced with deterministic placeholders and restored during `deobfuscate` via workspace metadata.

Current literal coverage:

- String literals and numeric literals are redacted.
- Date-like literals represented as strings are redacted.
- Boolean/NULL tokens are currently preserved.
- Numeric literals used as datatype parameters (for example `NUMERIC(10,2)`) are preserved.

Safety note:

- Redaction is AST-based (`sqlglot`) and not regex-only; regex-only redaction is intentionally not the primary privacy mechanism.

## Workspace Model

By default, `script.sql` produces a workspace `script.obf/`.

Typical workspace contents:

```text
script.obf/
|-- original.sql
|-- obfuscated.sql
|-- deobfuscated.sql                    # after deobfuscate/roundtrip
|-- llm_instructions.md
|-- mapping.json
|-- context.json
|-- integrity.json
|-- mapping.schema.json
|-- context.schema.json
|-- integrity.schema.json
|-- redaction.json                    # reversible redaction mode only
|-- redaction.schema.json             # reversible redaction mode only
`-- reports/
    |-- deobfuscation_report.json       # after deobfuscate/roundtrip
    |-- coverage_report.txt             # after deobfuscate/roundtrip
    |-- roundtrip_report.json           # after roundtrip
    |-- roundtrip_diff.txt              # after roundtrip --diff-report
    |-- original_pretty.sql             # normalized with sqlglot pretty formatting
    |-- deobfuscated_pretty.sql         # normalized with sqlglot pretty formatting
    `-- roundtrip_normalized_diff.txt   # diff of the normalized pair above
    |-- translation_report.schema.json  # after translate --workspace ...
    `-- translation_report.json         # after translate --workspace ...
```

## Integrity Protection

Workspace integrity is enforced with SHA-256 checksums in `integrity.json`.

Tracked files:

- `original.sql`
- `obfuscated.sql`
- `mapping.json`
- `context.json`
- `redaction.json` (reversible redaction mode only)

If checksums do not match, `deobfuscate`, `roundtrip`, and `workspace-info` fail with an integrity error.

## Command Reference

### `obfuscate`

```bash
python obfuscator.py obfuscate <input.sql|-> [options]
```

Options:

- `--workspace <dir>`: custom workspace path (default: `<input_stem>.obf`)
- `--dialect <name>`: parser dialect (default: `tsql`)
- `--seed <int>`: deterministic mapping seed
- `--pretty` / `--no-pretty`: formatted output on/off (default: `--pretty`)
- `--strict-go`: fail when a line starts with `GO` but is not a standalone batch separator line
- `--instruction-template <path>`: custom `llm_instructions.md` template
- `--strip-comments`: remove SQL comments from obfuscated output
- `--redact-literals`: redact string/numeric literals in obfuscated output
- `--redaction-mode <none|irreversible|reversible>`: redaction behavior (default: `none`)
- `--redaction-policy <all|strings-only|sensitive>`: literal redaction policy (default: `all`)
- `--redaction-sensitive-columns <csv>`: required when policy is `sensitive`
- `--stdout-only`: print obfuscated SQL to stdout without writing sibling output file
- `--output-dir <dir>`: write obfuscated output file into a specific directory (file input only)

Output:

- Prints obfuscated SQL to stdout
- Writes sibling output file `<input_stem>_obfuscated<ext>` (file input only, unless `--stdout-only` is used)
- Writes workspace artifacts
- If input is `-` (stdin), no sibling output file is written; workspace default is `stdin.obf`

### `deobfuscate`

```bash
python obfuscator.py deobfuscate --workspace <dir> --input <edited_obfuscated.sql> [options]
```

Options:

- `--out <path>`: output file path (default: `<workspace>/deobfuscated.sql`)
- `--dry-run`: analyze and print summary only; does not write output/report files
- `--allow-unresolved`: allow unknown/ambiguous mappings in non-dry-run mode and still write output/report files
- `--allow-low-confidence`: allow low-confidence mappings in non-dry-run mode and still write output/report files

Dry-run exit behavior:

- `0` when no unresolved identifier mappings and no unresolved reversible-redaction placeholders
- `1` when unresolved identifiers or unresolved reversible-redaction placeholders are found

Non-dry-run exit behavior:

- `0` when no unresolved mappings/placeholders and no low-confidence mappings are found
- `0` when unresolved mappings are explicitly overridden with `--allow-unresolved`
- `0` when low-confidence mappings are explicitly overridden with `--allow-low-confidence`
- `1` when unresolved mappings/placeholders are found without `--allow-unresolved`
- `1` when low-confidence mappings are found without `--allow-low-confidence`

Dry-run diagnostics also include resolver confidence:

- `low_confidence_count`
- `low_confidence_by_kind`

Low-confidence mappings are resolved heuristically and should be reviewed before production use.

### `validate-before-write`

```bash
python obfuscator.py validate-before-write --workspace <dir> --input <edited_obfuscated.sql> [options]
```

Behavior:

- Runs validation checks first (unresolved + low-confidence + reversible-redaction placeholder checks).
- Writes output/report artifacts only if checks pass (or are explicitly overridden).

Options:

- `--out <path>`: output file path (default: `<workspace>/deobfuscated.sql`)
- `--allow-unresolved`: explicit override for unresolved mapping checks
- `--allow-low-confidence`: explicit override for low-confidence mapping checks

### `roundtrip`

```bash
python obfuscator.py roundtrip <input.sql|-> [options]
```

Uses obfuscation options from `obfuscate` (`--workspace`, `--seed`, `--pretty`, etc.).

Additional option:

- `--diff-report`: writes unified diff to `reports/roundtrip_diff.txt`
- `--stdout-only`: skip sibling obfuscated output file write while still producing workspace/report artifacts
- `--output-dir <dir>`: write roundtrip obfuscated output file into a specific directory (file input only)

Roundtrip always writes a normalized comparison set:

- `reports/original_pretty.sql`
- `reports/deobfuscated_pretty.sql`
- `reports/roundtrip_normalized_diff.txt`

`roundtrip_report.json` includes both raw and normalized match metrics.
`roundtrip` returns non-zero if unresolved or low-confidence mappings are detected.

### `workspace-info`

```bash
python obfuscator.py workspace-info --workspace <dir>
```

Prints:

- workspace path
- dialect/seed/pretty
- batch/statement/mapping counts
- integrity algorithm and tracked-file count
- artifact/report presence flags

### `translate`

```bash
python obfuscator.py translate --input <input.sql|-> --source-dialect <dialect> --target-dialect <dialect> [options]
```

Options:

- `--out <path>`: output file path (default: `<input_stem>_<target_dialect>.sql`)
- `--pretty` / `--no-pretty`: formatted output on/off (default: `--pretty`)
- `--validate`: parse translated SQL with target dialect and fail on parse errors
- `--workspace <dir>`: optional path to persist `reports/translation_report.json`
- `--report-only`: write no translated SQL file; only print summary and optional report artifact
- `--stdout-only`: print translated SQL to stdout without writing translated SQL output files
- `--output-dir <dir>`: write translated SQL output file into a specific directory (file input only)

Output:

- Always prints `translate summary: source=... target=... statements=... failed=... warnings=...`
- Translated SQL is printed to stdout when `--stdout-only` is used
- For stdin input (`--input -`) with no `--out` and no `--output-dir`, translated SQL is printed to stdout
- Returns `0` when translation succeeds and optional validation passes
- Returns `1` on read/parse/translation/validation/report-write failures

## CI-Friendly Usage

- Validate LLM edits without file writes:
  - `python obfuscator.py deobfuscate --workspace run.obf --input run.obf/llm_response_obfuscated.sql --dry-run`
- Pipe SQL through translation:
  - `cat input.sql | python obfuscator.py translate --input - --source-dialect tsql --target-dialect hive`
- Keep generated SQL artifacts in dedicated folders:
  - `python obfuscator.py obfuscate input.sql --output-dir artifacts/sql`
  - `python obfuscator.py translate --input input.sql --source-dialect tsql --target-dialect hive --output-dir artifacts/sql`

## Usage Examples

### Basic Obfuscation

```bash
python obfuscator.py obfuscate sample_sql/01_simple_select.sql
```

### Explicit Subcommand Invocation

```bash
python obfuscator.py obfuscate sample_sql/01_simple_select.sql
```

### Deterministic Obfuscation

```bash
python obfuscator.py obfuscate sample_sql/02_joins.sql --seed 42
```

### Compact Output (No Pretty)

```bash
python obfuscator.py obfuscate sample_sql/06_aggregate_functions.sql --no-pretty
```

### Custom Workspace Location

```bash
python obfuscator.py obfuscate sample_sql/03_cte_example.sql --workspace .tmp/ws_cte
```

### Custom LLM Prompt Template

```bash
python obfuscator.py obfuscate sample_sql/04_temporary_tables.sql --instruction-template my_llm_prompt.md
```

### Redaction For LLM Sharing (Irreversible)

```bash
python obfuscator.py obfuscate script.sql --redaction-mode irreversible --redact-literals --strip-comments
```

### Selective Redaction Policy (Sensitive Columns Only)

```bash
python obfuscator.py obfuscate script.sql --redaction-mode irreversible --redact-literals --redaction-policy sensitive --redaction-sensitive-columns email,ssn,token
```

### Redaction For Roundtrip Restoration (Reversible)

```bash
python obfuscator.py obfuscate script.sql --redaction-mode reversible --redact-literals --strip-comments
python obfuscator.py deobfuscate --workspace script.obf --input script.obf/llm_response_obfuscated.sql --dry-run
python obfuscator.py deobfuscate --workspace script.obf --input script.obf/llm_response_obfuscated.sql
```

### De-obfuscate an LLM-Edited Script

```bash
python obfuscator.py deobfuscate --workspace sample_sql/06_aggregate_functions.obf --input sample_sql/06_aggregate_functions.obf/llm_response_obfuscated.sql
```

### De-obfuscate to Specific Output File

```bash
python obfuscator.py deobfuscate --workspace sample_sql/06_aggregate_functions.obf --input sample_sql/06_aggregate_functions.obf/llm_response_obfuscated.sql --out sample_sql/restored.sql
```

### De-obfuscation Dry-Run Validation

```bash
python obfuscator.py deobfuscate --workspace sample_sql/06_aggregate_functions.obf --input sample_sql/06_aggregate_functions.obf/llm_response_obfuscated.sql --dry-run
```

### Roundtrip Verification

```bash
python obfuscator.py roundtrip sample_sql/07_multiple_batches.sql
```

### Roundtrip with Diff Report

```bash
python obfuscator.py roundtrip sample_sql/07_multiple_batches.sql --diff-report
```

### Translate T-SQL to Hive

```bash
python obfuscator.py translate --input sample_sql/06_aggregate_functions.sql --source-dialect tsql --target-dialect hive --validate
```

### Translate Hive back to T-SQL

```bash
python obfuscator.py translate --input sample_sql/06_aggregate_functions_hive.sql --source-dialect hive --target-dialect tsql --validate
```

### Workspace Status and Integrity

```bash
python obfuscator.py workspace-info --workspace sample_sql/07_multiple_batches.obf
```

### Redirect Obfuscated Stdout

```bash
python obfuscator.py obfuscate sample_sql/08_schema_qualified.sql > output.sql
```

Note: this does not replace workspace/sibling file output; those are still written.

## Recommended LLM Workflow

1. Obfuscate:

```bash
python obfuscator.py obfuscate script.sql
```

2. Provide LLM with:

- `script.obf/obfuscated.sql`
- `script.obf/llm_instructions.md`

3. Save LLM output (example):

- `script.obf/llm_response_obfuscated.sql`

4. Validate first:

```bash
python obfuscator.py deobfuscate --workspace script.obf --input script.obf/llm_response_obfuscated.sql --dry-run
```

5. If clean, de-obfuscate fully:

```bash
python obfuscator.py deobfuscate --workspace script.obf --input script.obf/llm_response_obfuscated.sql
```

Recommended privacy-oriented variant:

```bash
python obfuscator.py obfuscate script.sql --redaction-mode reversible --redact-literals --strip-comments
```

### Cross-Dialect LLM Workflow

1. Obfuscate source dialect script:

```bash
python obfuscator.py obfuscate script.sql --dialect tsql
```

2. Translate obfuscated SQL to target dialect:

```bash
python obfuscator.py translate --input script_obfuscated.sql --source-dialect tsql --target-dialect hive --validate
```

3. Translate edited SQL back to source dialect before de-obfuscation:

```bash
python obfuscator.py translate --input edited_hive.sql --source-dialect hive --target-dialect tsql --validate
```

4. De-obfuscate against the original workspace mapping:

```bash
python obfuscator.py deobfuscate --workspace script.obf --input edited_tsql.sql --dry-run
```

## Troubleshooting

### Unknown Identifiers

Symptoms:

- `unknown_count > 0` in dry-run output/report.

Meaning:

- LLM likely introduced new identifiers or renamed obfuscated ones.

Actions:

1. Ask LLM to preserve obfuscated identifiers exactly.
2. Check `unknown_by_kind` in reports for where it happened.
3. Re-run `--dry-run` before final de-obfuscation.

### Ambiguous Identifiers

Symptoms:

- `ambiguous_count > 0`.

Meaning:

- Scope/alias rewrites made reverse mapping non-unique.

Actions:

1. Ask LLM to keep alias/table structure closer to input.
2. Avoid unnecessary alias rewrites.
3. Re-validate with `--dry-run`.

### Low-Confidence Mappings

Symptoms:

- `low_confidence_count > 0` in dry-run output/report.

Meaning:

- Identifier mapping succeeded, but resolver had to use relaxed/heuristic matching due to structural rewrite drift.

Actions:

1. Review de-obfuscated SQL manually before execution.
2. Ask LLM to keep alias/table structure closer to obfuscated input.
3. Re-run `--dry-run` after tightening prompt constraints.
4. Only if you explicitly accept the risk, run with `--allow-low-confidence`.

### Integrity Check Failed

Symptoms:

- Error includes checksum mismatch for a workspace artifact.

Meaning:

- One protected workspace file changed after creation.

Actions:

1. Restore workspace from trusted copy, or
2. Re-obfuscate to generate a fresh workspace and retry workflow.

### Reversible Redaction Placeholders Unresolved

Symptoms:

- Dry-run shows `redaction_unknown_placeholder_count > 0` or `redaction_missing_placeholder_count > 0`.

Meaning:

- LLM output changed or removed placeholder literals produced by reversible redaction.

Actions:

1. Ask the LLM to preserve placeholder literals exactly.
2. Re-run `deobfuscate --dry-run` and verify both redaction counters are zero.
3. If placeholders were heavily rewritten, re-obfuscate and retry with stricter prompt instructions.

### Translation Failed or Validation Failed

Symptoms:

- `translate summary` shows `failed > 0`, or translate returns exit code `1`.

Meaning:

- Source parsing failed, statement emission failed, or `--validate` target parsing failed.

Actions:

1. Re-run with `--workspace` and inspect `reports/translation_report.json`.
2. Narrow down the failing statement using `batch_index`/`statement_index` in the report.
3. Translate in smaller sections when dealing with unsupported dialect-specific syntax.

## Current Limits

- `--strict-go` currently validates T-SQL `GO` separators only when `GO` starts a line; use standalone `GO` lines in strict mode.
- `--output-dir` is supported for file inputs only (not stdin).
- `--stdout-only` cannot be combined with `--output-dir`.
- For `translate`, `--stdout-only` cannot be combined with `--out` or `--report-only`.
- For `translate`, `--out` cannot be combined with `--output-dir`.
- Comments/formatting can change due to SQL regeneration (`sqlglot` output style).
- The tool targets identifier round-trip behavior, not byte-for-byte source reconstruction.
- Translation is structural via `sqlglot`, not a semantic equivalence guarantee.

## Development

Run tests:

```bash
pytest
```

Run a subset:

```bash
pytest tests/test_cli.py -q
pytest tests/test_deobfuscation.py -q
pytest tests/test_llm_workflow_integration.py -q
```
