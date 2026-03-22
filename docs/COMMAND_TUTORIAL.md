# SQL Obfuscator Command Tutorial

This tutorial walks through common workflows from simple to advanced.
Each section includes:

- a small SQL example
- what the command does
- the command and key flags
- what result to expect

Note on examples:

- The SQL output examples below were captured from real CLI runs.
- The identifier replacements in the current generator are adjective-animal combinations.
- If `--seed` is not set, exact generated identifier names can differ between runs.
- The app uses `sqlglot` to parse, and the SQL output is formatted with the option `pretty=True`, meaning the SQL output in the examples below doesn't keep the format used in the SQL input.
- You can use `-` as input for `obfuscate`, `roundtrip`, and `translate --input -` to read SQL from stdin.
- You can use `--stdout-only` to print SQL output without writing sibling/default SQL output files.
- `--output-dir` is for file inputs, and cannot be combined with `--stdout-only`.
- For `translate`, `--out` cannot be combined with `--output-dir`, and `--stdout-only` cannot be combined with `--report-only`.
- Some advanced procedural T-SQL constructs may emit a summarized `sqlglot used fallback parsing ...` notice; treat that as diagnostic output, not an automatic failure.

## Key Terms (used throughout)

- `workspace`: a run folder (usually `<input-stem>.obf`) that stores inputs, outputs, and metadata for later commands.
- `artifact`: a file produced by the tool (for example `mapping.json` or `deobfuscated.sql`).
- `mapping`: identifier lookup data that connects obfuscated names back to original names.
- `context`: metadata about the run (for example dialect, statement counts, formatting mode) used during restore/validation.
- `integrity tracking`: checksum validation that detects changed/tampered workspace artifacts.
- `placeholder`: a temporary token used in reversible literal redaction so original literal values can be restored.
- `dialect`: SQL flavor (`tsql`, `hive`) used for parsing and output generation.
- `statement anchor`: stable per-statement metadata attached to one statement in the obfuscated script. It gives that statement an ID such as `stmt_0001` and helps the tool match edits/restores back to the right place.
- `statement replacement`: a structured JSON edit that says "replace statement X with this SQL" instead of asking the LLM to rewrite the whole file.
- `bounded external LLM sharing`: the conservative workflow used when obfuscated SQL will be sent to an LLM outside your immediate trust boundary, such as a hosted API. `bounded` means the model is expected to make small, local edits while keeping obfuscated identifiers, placeholders, and overall structure stable.
- `fail closed`: stop with an error instead of continuing when a safety condition is not met. In this tool, `--llm-safe` uses fail-closed behavior.
- `expert mode`: the less-constrained workflow where you intentionally allow larger rewrites or manual full-script edits and accept that more review may be needed afterward.
- `unresolved`: the tool could not confidently map an obfuscated identifier/placeholder back to an original value.
- `ambiguous`: multiple possible restore targets exist, so the tool cannot safely choose one.
- `low-confidence`: a best match was found, but with reduced confidence due to structural edits.
- `override flag`: an explicit opt-in flag (for example `--allow-unresolved`) that allows writing output despite safety warnings.

## Jump to Use Case

- New user quick start: [1) Basic obfuscation](#s1)
- Reproducible output for tests/reviews: [2) Deterministic obfuscation with `--seed`](#s2)
- Keep outputs isolated by run: [3) Custom workspace path](#s3)
- Share safely with LLM (no restoration needed): [4) Irreversible redaction](#s4)
- Share with LLM and restore literals later: [5) Reversible redaction + restore](#s5)
- Preferred bounded LLM edit application: [5a) `apply-llm-edits`](#s5a)
- Validate edited SQL without writing output: [6) Safety check with `deobfuscate --dry-run`](#s6)
- Validate first, write only on pass: [7) `validate-before-write`](#s7)
- Quick quality check in one command: [8) `roundtrip`](#s8)
- Cross-dialect conversion: [9) `translate`](#s9)
- Inspect workspace/report health: [10) `workspace-info`](#s10)
- Control where SQL outputs are written: [11) `--stdout-only` and `--output-dir`](#s11)
- Use installed command instead of wrapper script: [12) Installed CLI (`sql-obfuscator`)](#s12)
- Pipe workflows without temp files: [13) Stdin pipeline workflows](#s13)
- Choose the right translate write mode: [14) `translate` output mode matrix](#s14)
- Enforce strict batch separator handling: [15) `--strict-go` pass/fail examples](#s15)
- Diagnose failures quickly: [16) Troubleshooting by exit code](#s16)

<a id="s1"></a>

## 1) Basic obfuscation

SQL input:

```sql
SELECT customer_id, email
FROM sales.customers
WHERE status = 'active';
```

What this does:

- Obfuscates identifiers (table/column/aliases/etc.).
- Creates a default workspace (`<input-stem>.obf`, the run folder) with mapping/context artifacts (generated metadata files).

Command:

```bash
python obfuscator.py obfuscate sample.sql
```

Command options used:

- none (baseline behavior)

Expected result:

- `sample_obfuscated.sql` is written.
- `sample.obf/` is created with `original.sql`, `obfuscated.sql`, `mapping.json`, `context.json`, integrity artifacts, and instructions template.

Example expected SQL output (`sample_obfuscated.sql`):

```sql
SELECT
  dog,
  ferret
FROM sales.fox
WHERE
  gazelle = 'active'
```

<a id="s2"></a>

## 2) Deterministic obfuscation with `--seed`

SQL input:

```sql
SELECT o.order_id, o.total_amount
FROM orders o;
```

What this does:

- Produces reproducible obfuscation tokens for the same input + seed.

Command:

```bash
python obfuscator.py obfuscate sample.sql --seed 42
```

Command options used:

- `--seed 42`: stabilize obfuscated name generation for repeatable outputs.

Expected result:

- Re-running with the same seed and same input yields the same obfuscated identifiers.

Example expected SQL output (`sample_obfuscated.sql`):

```sql
SELECT
  cougar.penguin,
  cougar.bat
FROM skunk AS cougar
```

<a id="s3"></a>

## 3) Custom workspace path

SQL input:

```sql
WITH recent_orders AS (
  SELECT order_id, customer_id
  FROM orders
)
SELECT customer_id
FROM recent_orders;
```

What this does:

- Writes workspace artifacts (generated files) to a chosen folder.

Command:

```bash
python obfuscator.py obfuscate sample.sql --workspace runs/demo_01.obf
```

Command options used:

- `--workspace runs/demo_01.obf`: output workspace folder override.

Expected result:

- Workspace artifacts are written to `runs/demo_01.obf` instead of `sample.obf`.

Example expected SQL output (`sample_obfuscated.sql`):

```sql
WITH camel AS (
  SELECT
    gorilla AS gorilla,
    jay AS jay
  FROM buffalo
)
SELECT
  jay
FROM camel
```

<a id="s4"></a>

## 4) Irreversible redaction for safe sharing

SQL input:

```sql
-- analyst note: priority account
SELECT customer_id, email
FROM customers
WHERE email = 'alice@example.com'
  AND credit_limit > 5000;
```

What this does:

- Obfuscates identifiers.
- Strips comments.
- Redacts literals for LLM sharing, without storing restore mapping data.
- Fails closed when parser fallback/raw passthrough leaves statements that are not approved for bounded external LLM sharing.

Plain-language note:

- `Fails closed` means the command stops with an error instead of continuing and producing a workspace that might be mistaken for safe-to-share output.
- `Bounded external LLM sharing` means a cautious workflow for sending obfuscated SQL to an outside LLM while expecting edit-sized changes, not a full rewrite of the script.

Command:

```bash
python obfuscator.py obfuscate sample.sql \
  --llm-safe \
  --redaction-mode irreversible \
  --redact-literals \
  --strip-comments
```

Command options used:

- `--llm-safe`: reject workspaces that still contain fallback/raw-passthrough statements not approved for bounded external LLM sharing.
- `--redaction-mode irreversible`: privacy-first sanitization, no literal restoration.
- `--redact-literals`: redact literal values.
- `--strip-comments`: remove comments from output.

Expected result:

- Obfuscated SQL has no original comments/literals.
- Workspace includes `reports/llm_workflow_report.json` with LLM-sharing safety diagnostics.
- `deobfuscate` restores identifiers only; literal values remain sanitized.

Example expected SQL output (`sample_obfuscated.sql`):

```sql
SELECT
  gorilla,
  pigeon
FROM gazelle
WHERE
  pigeon = '<REDACTED_STR>' AND llama > 0
```

<a id="s5"></a>

## 5) Reversible redaction and literal restoration

In this example, the original SQL script (SQL input) is first obfuscated, and then de-obfuscated. This can be used to test the application or, in the recommended LLM workflow, to give the obfuscated SQL to an LLM, let the LLM return structured statement replacements, apply those replacements with `apply-llm-edits`, and then de-obfuscate the resulting script. The result has the same column names/table names/aliases/etc. as the original script.

SQL input:

```sql
SELECT account_id
FROM payments
WHERE card_last4 = '1234'
  AND amount > 250.00;
```

What this does:

- Redacts literals with deterministic placeholders (stable temporary tokens).
- Saves redaction metadata so literals can be restored during de-obfuscation.

Command (obfuscate):

```bash
python obfuscator.py obfuscate sample.sql \
  --llm-safe \
  --redaction-mode reversible \
  --redact-literals
```

Command (de-obfuscate edited file):

```bash
python obfuscator.py deobfuscate \
  --workspace sample.obf \
  --input sample.obf/llm_response_obfuscated.sql
```

Command options used:

- `--llm-safe`: recommended when the obfuscated SQL will be shared with an external LLM.
- `--redaction-mode reversible`: enable reversible literal placeholders.
- `--redact-literals`: apply literal redaction pass.

Expected result:

- Workspace includes `redaction.json` and `redaction.schema.json`.
- Workspace includes `llm_instructions.md` with statement IDs and the preferred `statement_replacements` JSON format.
- If placeholders survive the LLM edit, literals are restored in final de-obfuscated SQL.
- If placeholders are broken, safety checks fail unless explicitly overridden.

Example expected SQL output after `deobfuscate`:

```sql
SELECT
  account_id
FROM payments
WHERE
  card_last4 = '1234' AND amount > 250.00
```

<a id="s5a"></a>

## 5a) Preferred bounded-edit application with `apply-llm-edits`

`apply-llm-edits` is the bridge between obfuscation and de-obfuscation in the recommended LLM workflow. You normally use it after the LLM has responded, but before running `deobfuscate` or `validate-before-write`.

Why this command exists:

- It gives the LLM a narrower job: change only the statements you intend to change.
- It preserves every untouched statement exactly as it appeared in `obfuscated.sql`.
- It catches common response mistakes early, before restore is attempted.
- It reduces the chance of structural drift that can lead to low-confidence or unresolved restore results.

Where it fits in the workflow:

1. `obfuscate` creates `obfuscated.sql`, `context.json`, and `llm_instructions.md`.
2. The LLM reads `obfuscated.sql` and `llm_instructions.md`.
3. The LLM returns `llm_edits.json` using the `statement_replacements` format.
4. `apply-llm-edits` validates that payload and writes `llm_response_obfuscated.sql`.
5. `deobfuscate --dry-run` or `validate-before-write` then uses `llm_response_obfuscated.sql` as input.

LLM input/output in the recommended workflow:

- Give the LLM `sample.obf/obfuscated.sql` and `sample.obf/llm_instructions.md`.
- Ask it to return JSON `statement_replacements` instead of a full rewritten script.
- Each edit targets one known `statement_id` and must contain exactly one replacement SQL statement that still uses the obfuscated identifiers from the workspace.
- In practical terms, this means the LLM should keep the obfuscated table names, column names, aliases, and any placeholder literals it sees unless the change truly requires otherwise.

Example `sample.obf/llm_edits.json`:

```json
{
  "schema_version": 1,
  "format": "statement_replacements",
  "edits": [
    {
      "statement_id": "stmt_0002",
      "sql": "SELECT [spruce_hyena] FROM dbo.sleepy_gerbil WHERE 1 = 1 AND [spruce_hyena] > 10"
    }
  ]
}
```

What this does:

- Validates that each edit references a known `statement_id` from the workspace instructions/context.
- Validates that each `sql` value contains exactly one statement, so one edit cannot silently rewrite multiple statements.
- Rebuilds `llm_response_obfuscated.sql` while preserving untouched statements exactly from `obfuscated.sql`.
- Writes an edit-application report you can inspect before restore.

When to use this command:

- Use it for the normal LLM-assisted workflow where the model is making targeted statement-level changes.
- Use it when you want a safer handoff between the LLM output and the restore step.
- Prefer it over manual full-file editing whenever the requested SQL change can be expressed as one or more statement replacements.

When you might not use it:

- If you are intentionally doing an expert-mode full-script rewrite and accept the extra review/risk that comes with broader structural edits.

Command:

```bash
python obfuscator.py apply-llm-edits \
  --workspace sample.obf \
  --edits sample.obf/llm_edits.json
```

Command options used:

- `--workspace sample.obf`: workspace containing `obfuscated.sql`, `context.json`, and statement anchors.
- `--edits sample.obf/llm_edits.json`: JSON edits returned by the LLM, either raw JSON or a fenced `json` code block.
- `--out <path>`: optional output path for the rebuilt obfuscated SQL.
- `--dry-run`: validate the edit payload and print a summary without writing files.

Expected result:

- `sample.obf/llm_response_obfuscated.sql` is written by default. This is the file you usually pass to `deobfuscate --dry-run` or `validate-before-write` next.
- `sample.obf/reports/llm_edit_application_report.json` is written after a non-dry-run apply.
- Untouched statements remain byte-for-byte identical to the original `obfuscated.sql`, which is the main safety advantage of this workflow.
- The command fails fast for unknown `statement_id` values, duplicate edits, stale workspaces without anchor SQL, parse errors, or multi-statement replacements.

### Optional selective redaction policies

Command:

```bash
python obfuscator.py obfuscate sample.sql \
  --redaction-mode irreversible \
  --redact-literals \
  --redaction-policy sensitive \
  --redaction-sensitive-columns email,ssn,token
```

Command options used:

- `--redaction-policy all|strings-only|sensitive`: choose literal redaction scope.
- `--redaction-sensitive-columns ...`: required when policy is `sensitive`.

Expected result:

- Only configured sensitive-column literals are redacted in `sensitive` mode.

Example expected SQL output (`sample_obfuscated.sql`):

```sql
SELECT
  lemur,
  crane
FROM octopus
WHERE
  crane = '<REDACTED_STR>' AND gazelle = 'ACTIVE'
```

<a id="s6"></a>

## 6) Safety check with `deobfuscate --dry-run`

SQL input (usually produced by `apply-llm-edits` in the recommended workflow):

```sql
SELECT t1.c1
FROM t1
WHERE t1.c2 = 'changed_by_llm';
```

What this does:

- Runs mapping resolution (matching obfuscated names back to originals) and redaction placeholder checks.
- Reuses the same de-obfuscation safety logic that `validate-before-write` uses later.
- Prints diagnostics only; does not write de-obfuscated output.

Command:

```bash
python obfuscator.py deobfuscate \
  --workspace sample.obf \
  --input sample.obf/llm_response_obfuscated.sql \
  --dry-run
```

Command options used:

- `--dry-run`: validation mode, report summary only.

Expected result:

- Summary includes unknown/ambiguous/low-confidence counts and redaction placeholder diagnostics.
- Exit code is non-zero when unresolved issues are present.

Example expected SQL output:

```sql
-- No SQL output file is written in dry-run mode.
```

<a id="s7"></a>

## 7) `validate-before-write`

SQL input (usually produced by `apply-llm-edits` in the recommended workflow):

```sql
SELECT t1.c1
FROM t1
WHERE t1.c2 = 'value';
```

What this does:

- Validation-first path: runs checks, writes output only when safety checks pass.
- Gives you the safest single-command finalization step after a clean edit-application pass.

Command:

```bash
python obfuscator.py validate-before-write \
  --workspace sample.obf \
  --input sample.obf/llm_response_obfuscated.sql
```

Command options used:

- same base inputs as `deobfuscate`, but command enforces validation-first workflow.

Expected result:

- Writes `deobfuscated.sql` only if no unresolved mappings/placeholders and no low-confidence violations (unless explicit overrides are passed).
- Works especially well after `apply-llm-edits`, because untouched obfuscated statements are preserved exactly.

Example expected SQL output (`deobfuscated.sql`):

```sql
SELECT
  customer_id
FROM customers
WHERE
  status = 'value'
```

<a id="s8"></a>

## 8) `roundtrip` verification loop

SQL input:

```sql
SELECT department_id, COUNT(*) AS employee_count
FROM employees
GROUP BY department_id;
```

What this does:

- Obfuscates then immediately de-obfuscates.
- Emits comparison artifacts (report/diff files) for verification.

Command:

```bash
python obfuscator.py roundtrip sample.sql --diff-report
```

Command options used:

- `--diff-report`: writes textual diff artifacts for inspection.
- `--strict-go` (optional): fail if `GO` appears in unsupported non-standalone forms when strict batch handling is required.

Expected result:

- Workspace report files include roundtrip comparison outputs.
- `reports/original_pretty.sql`, `reports/deobfuscated_pretty.sql`, and `reports/roundtrip_normalized_diff.txt` show the normalized semantic comparison set.
- If raw SQL differs only by formatting/comments and the normalized pair matches, `reports/roundtrip_diff.txt` contains a short summary instead of a noisy unified diff.
- Non-zero exit if unresolved/ambiguous/low-confidence issues (or redaction placeholder issues) are detected.

Example expected SQL output (`deobfuscated.sql` from roundtrip):

```sql
SELECT
  department_id,
  COUNT(*) AS employee_count
FROM employees
GROUP BY
  department_id
```

<a id="s9"></a>

## 9) Translate between dialects

SQL input:

```sql
SELECT TOP 10 customer_id, total_amount
FROM orders
ORDER BY created_at DESC;
```

What this does:

- Converts SQL from one supported dialect (SQL flavor) to another and optionally validates parseability.

Command:

```bash
python obfuscator.py translate \
  --input sample.sql \
  --source-dialect tsql \
  --target-dialect hive \
  --validate
```

Command options used:

- `--source-dialect`, `--target-dialect`: conversion direction.
- `--validate`: parse translated output in target dialect.

Expected result:

- A translated SQL output file is written unless `--report-only` or `--stdout-only` is used.
- Translation summary reports statement failures/warnings.

Example expected SQL output (`sample_hive.sql`):

```sql
SELECT
  customer_id,
  total_amount
FROM orders
ORDER BY
  created_at DESC
LIMIT 10
```

<a id="s10"></a>

## 10) Workspace-info and integrity status

What this does:

- Displays workspace metadata and artifact presence.
- Validates integrity tracking before reporting status.

Command:

```bash
python obfuscator.py workspace-info --workspace sample.obf
```

Command options used:

- `--workspace`: target workspace folder.

Expected result:

- Prints dialect/seed/statement stats, statement-anchor count, and artifact/report availability.
- Shows whether reports such as `llm_workflow_report.json` and `llm_edit_application_report.json` are present.
- Confirms integrity state for tracked files.

Example expected SQL output:

```sql
-- This command prints workspace/report metadata; it does not generate SQL output.
```

<a id="s11"></a>

## 11) `--stdout-only` and `--output-dir`

SQL input:

```sql
SELECT UserId, UserName
FROM Users;
```

What this does:

- `--stdout-only`: prints SQL output without creating default sibling SQL output files.
- `--output-dir`: writes generated SQL output files to a chosen directory for CI/artifact collection.

Commands:

```bash
# Print obfuscated SQL only, still create workspace artifacts
python obfuscator.py obfuscate sample.sql --stdout-only

# Write obfuscated output file into artifacts/sql/
python obfuscator.py obfuscate sample.sql --output-dir artifacts/sql

# Print the summary plus translated SQL
python obfuscator.py translate --input sample.sql --source-dialect tsql --target-dialect hive --stdout-only

# Write translated SQL into artifacts/sql/
python obfuscator.py translate --input sample.sql --source-dialect tsql --target-dialect hive --output-dir artifacts/sql
```

Expected result:

- `--stdout-only` skips default sibling output SQL files.
- `--output-dir` writes SQL files into the specified directory.
- Both modes keep normal command validation/exit behavior.

<a id="s12"></a>

## 12) Installed CLI (`sql-obfuscator`)

What this does:

- Uses the installable console entry point instead of `python obfuscator.py`.
- Keeps command behavior and flags identical.

Commands:

```bash
# Show top-level help
sql-obfuscator --help

# Obfuscate
sql-obfuscator obfuscate sample.sql

# Translate and validate
sql-obfuscator translate --input sample.sql --source-dialect tsql --target-dialect hive --validate
```

Expected result:

- Same outputs and exit behavior as wrapper-script invocation.
- Useful for CI/dev environments where the package is installed in a virtual environment.

<a id="s13"></a>

## 13) Stdin pipeline workflows

SQL input source (shell pipeline):

```sql
SELECT account_id, token
FROM auth.sessions;
```

What this does:

- Runs commands without creating an input file.
- Supports automation where SQL is streamed from another process.

Commands:

```bash
# Obfuscate from stdin (workspace defaults to stdin.obf)
cat sample.sql | python obfuscator.py obfuscate - --seed 42

# Roundtrip from stdin with diff artifact
cat sample.sql | python obfuscator.py roundtrip - --diff-report

# Translate from stdin and print translated SQL
cat sample.sql | python obfuscator.py translate --input - --source-dialect tsql --target-dialect hive
```

Expected result:

- `obfuscate -` and `roundtrip -` create `stdin.obf/` unless `--workspace` is provided.
- No sibling file such as `*_obfuscated.sql` is created for stdin input.
- `translate --input -` prints translated SQL to stdout when `--out` and `--output-dir` are not set.

<a id="s14"></a>

## 14) `translate` output mode matrix

What this does:

- Clarifies where translated SQL is written/printed for each output mode.
- Makes invalid flag combinations explicit for predictable CI behavior.

Commands:

```bash
# Default: writes sibling output file
python obfuscator.py translate --input sample.sql --source-dialect tsql --target-dialect hive

# Explicit output file
python obfuscator.py translate --input sample.sql --source-dialect tsql --target-dialect hive --out out/hive.sql

# Output directory mode
python obfuscator.py translate --input sample.sql --source-dialect tsql --target-dialect hive --output-dir artifacts/sql

# Stdout-only mode
python obfuscator.py translate --input sample.sql --source-dialect tsql --target-dialect hive --stdout-only

# Report-only mode (no translated SQL write)
python obfuscator.py translate --input sample.sql --source-dialect tsql --target-dialect hive --report-only
```

Expected result:

- Default/file input: translated SQL file is written next to input.
- `--out`: translated SQL is written only to the specified path.
- `--output-dir`: translated SQL is written in the specified directory.
- `--stdout-only`: translated SQL is printed after the summary line, and no translated SQL file is written, including workspace `translated.sql`.
- `--report-only`: no translated SQL file is written; summary/report artifacts only.
- Invalid combinations fail fast:
  - `--out` + `--output-dir`
  - `--stdout-only` + `--report-only`
  - `--stdout-only` + `--out`
  - `--stdout-only` + `--output-dir`

<a id="s15"></a>

## 15) `--strict-go` pass/fail examples

SQL input (valid strict case):

```sql
SELECT 1;
GO
SELECT 2;
```

SQL input (invalid strict case):

```sql
SELECT 1; GO
SELECT 2;
```

What this does:

- Enforces strict handling of T-SQL `GO` batch separators.
- Fails when `GO` is used in unsupported non-standalone form.

Commands:

```bash
# Valid strict usage
python obfuscator.py obfuscate valid_go.sql --strict-go

# Invalid strict usage (expected failure)
python obfuscator.py obfuscate invalid_go.sql --strict-go
```

Expected result:

- Valid case succeeds and writes normal artifacts.
- Invalid case exits non-zero with a strict-go validation error.
- Without `--strict-go`, backward-compatible behavior is preserved.

<a id="s16"></a>

## 16) Troubleshooting by exit code

What this does:

- Provides a fast path to classify failures during local runs and CI.
- Maps common non-zero exits to likely causes and next actions.

Exit code guide:

- `0`: command succeeded.
- `1`: command failed due to input/validation/runtime errors.

Common failure patterns and actions:

- `apply-llm-edits` fails:
  - Cause: unknown `statement_id`, duplicate `statement_id`, multi-statement replacement SQL, parse error in replacement SQL, or a stale workspace that does not contain exact statement-anchor SQL.
  - Action: inspect `llm_instructions.md`, confirm the LLM returned the preferred `statement_replacements` JSON format, make sure each `sql` value is exactly one obfuscated SQL statement, then re-run `obfuscate` if the workspace was produced by an older version.
- `deobfuscate` or `validate-before-write` fails:
  - Cause: unresolved/ambiguous/low-confidence mappings, missing placeholders, or integrity issues.
  - Action: run `workspace-info`, then run `deobfuscate --dry-run` to inspect summary counts before deciding on override flags.
- `translate` fails:
  - Cause: source parse errors, target emission/validation errors, or invalid flag combinations.
  - Action: retry with `--workspace` and inspect `reports/translation_report.json`; remove conflicting flags (`--out` + `--output-dir`, `--stdout-only` combinations).
- `obfuscate`/`roundtrip` fails with strict GO mode:
  - Cause: `GO` used in non-standalone form while `--strict-go` is enabled.
  - Action: rewrite to standalone `GO` lines or rerun without `--strict-go` if strict enforcement is not required.
- `workspace-info` fails:
  - Cause: workspace path missing or required artifacts/checksums invalid.
  - Action: verify workspace path, then regenerate workspace from the original input if integrity artifacts are missing/tampered.

## Common safe workflow (recommended)

1. Obfuscate with the desired redaction policy and `--llm-safe` when the output will be shared externally.
2. Give the LLM `obfuscated.sql` and `llm_instructions.md`.
3. Save the LLM response as `llm_edits.json` in the preferred `statement_replacements` JSON format.
4. Run `apply-llm-edits` to build `llm_response_obfuscated.sql` while preserving untouched statements exactly.
5. Run `deobfuscate --dry-run` first.
6. Run `validate-before-write` for validation-first output generation.
7. Use override flags only with explicit human review.
