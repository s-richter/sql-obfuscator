# SQL Obfuscator Command Tutorial

This tutorial walks through common workflows from simple to advanced.
Each section includes:

- a small SQL example
- what the command does
- the command and key flags
- what result to expect

Note on examples:

- The SQL output examples below were captured from real CLI runs.
- The identifier replacements right now (2026-02-21) are animal based.
- If `--seed` is not set, exact animal identifier names can differ between runs.
- The app uses `sqlglot` to parse, and the SQL output is formatted with the option `pretty=True`, meaning the SQL output in the examples below doesn't keep the format used in the SQL input.

## Key Terms (used throughout)

- `workspace`: a run folder (usually `<input-stem>.obf`) that stores inputs, outputs, and metadata for later commands.
- `artifact`: a file produced by the tool (for example `mapping.json` or `deobfuscated.sql`).
- `mapping`: identifier lookup data that connects obfuscated names back to original names.
- `context`: metadata about the run (for example dialect, statement counts, formatting mode) used during restore/validation.
- `integrity tracking`: checksum validation that detects changed/tampered workspace artifacts.
- `placeholder`: a temporary token used in reversible literal redaction so original literal values can be restored.
- `dialect`: SQL flavor (`tsql`, `hive`) used for parsing and output generation.
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
- Validate edited SQL without writing output: [6) Safety check with `deobfuscate --dry-run`](#s6)
- Validate first, write only on pass: [7) `validate-before-write`](#s7)
- Quick quality check in one command: [8) `roundtrip`](#s8)
- Cross-dialect conversion: [9) `translate`](#s9)
- Inspect workspace/report health: [10) `workspace-info`](#s10)

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

Command:

```bash
python obfuscator.py obfuscate sample.sql \
  --redaction-mode irreversible \
  --redact-literals \
  --strip-comments
```

Command options used:

- `--redaction-mode irreversible`: privacy-first sanitization, no literal restoration.
- `--redact-literals`: redact literal values.
- `--strip-comments`: remove comments from output.

Expected result:

- Obfuscated SQL has no original comments/literals.
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

In this example, the original SQL script (SQL input) is first obfuscated, and then de-obfuscated. This can be used to test the application or, as shown in later examples, used to give the obfuscated SQL to an LLM, let the LLM edit the SQL, and then de-obfuscate the edited SQL. The result has the same column names/table names/aliases/etc. as the original script.

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

- `--redaction-mode reversible`: enable reversible literal placeholders.
- `--redact-literals`: apply literal redaction pass.

Expected result:

- Workspace includes `redaction.json` and `redaction.schema.json`.
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

SQL input (LLM-edited obfuscated SQL):

```sql
SELECT t1.c1
FROM t1
WHERE t1.c2 = 'changed_by_llm';
```

What this does:

- Runs mapping resolution (matching obfuscated names back to originals) and redaction placeholder checks.
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

SQL input (LLM-edited obfuscated SQL):

```sql
SELECT t1.c1
FROM t1
WHERE t1.c2 = 'value';
```

What this does:

- Validation-first path: runs checks, writes output only when safety checks pass.

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

Expected result:

- Workspace report files include roundtrip comparison outputs.
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

- A translated SQL output file is written (unless `--report-only`).
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

- Prints dialect/seed/statement stats and artifact/report availability.
- Confirms integrity state for tracked files.

Example expected SQL output:

```sql
-- This command prints workspace/report metadata; it does not generate SQL output.
```

## Common safe workflow (recommended)

1. Obfuscate with desired redaction policy.
2. Send obfuscated SQL to LLM.
3. Run `deobfuscate --dry-run` first.
4. Run `validate-before-write` for validation-first output generation.
5. Use override flags only with explicit human review.
