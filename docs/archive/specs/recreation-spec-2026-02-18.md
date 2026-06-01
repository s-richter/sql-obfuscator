# SQL Obfuscator Re-Creation Specification (Historical Snapshot)

> [!WARNING]
> This document is a historical snapshot from 2026-02-18. It does not describe
> the current application contract and must not be used to rebuild current
> feature parity. For maintained usage documentation, see `README.md` and
> `docs/guides/command-tutorial.md`. For exact behavior, use the current source and
> tests.

This document preserves the application state captured on 2026-02-18 for
historical reference.

## 1. Product Summary
- Name: `sql-obfuscator`
- Language: Python 3.10+
- Core dependency: `sqlglot` (runtime currently pinned in `requirements.txt` to `>=28,<29`)
- Purpose: Obfuscate SQL identifiers in T-SQL scripts, persist reversible mapping/context, support de-obfuscation of edited obfuscated SQL, and provide workspace/report artifacts for LLM workflows.

## 2. Top-Level Capabilities
- AST-based obfuscation of identifier classes:
  - tables (including `#temp` and `##global temp`)
  - columns
  - CTE names
  - table aliases
  - projection aliases (`AS Alias`)
  - column definitions (`CREATE TABLE ...`)
  - insert target columns (`INSERT INTO T (col1, ...)`)
- Deterministic output via `--seed`
- Multi-batch handling with standalone `GO` separators
- Reversible workspace model:
  - obfuscate -> save mapping/context/integrity
  - deobfuscate edited obfuscated SQL using saved mapping/context
- Integrity enforcement (`sha256`) over critical artifacts
- CLI modes:
  - legacy invocation: `python obfuscator.py <sql_file>`
  - subcommands: `obfuscate`, `deobfuscate`, `roundtrip`, `workspace-info`

## 3. Repository Structure (Behavioral)
- Entrypoint:
  - `obfuscator.py` (adds `src/` to `sys.path`, calls `sql_obfuscator.cli.main`)
- Core modules:
  - `src/sql_obfuscator/cli.py`
  - `src/sql_obfuscator/pipeline.py`
  - `src/sql_obfuscator/transformer.py`
  - `src/sql_obfuscator/registry.py`
  - `src/sql_obfuscator/deobfuscation.py`
  - `src/sql_obfuscator/workspace.py`
  - `src/sql_obfuscator/go_batches.py`
  - `src/sql_obfuscator/names.py`
  - `src/sql_obfuscator/errors.py`
- Data files:
  - `src/sql_obfuscator/identifier_replacements.txt`
  - `src/sql_obfuscator/tsql_reserved_keywords.txt`
- Fixtures:
  - `sample_sql/*.sql`
- Test suite:
  - `tests/*.py`

## 4. CLI Contract

### 4.1 Legacy Mode
- If argv first token is not a recognized subcommand, parse as legacy mode:
  - `python obfuscator.py <sql_file> [obfuscation options]`
- Equivalent behavior to `obfuscate` subcommand.

### 4.2 Subcommands
- `obfuscate <sql_file> [options]`
- `deobfuscate --workspace <dir> --input <edited_obfuscated.sql> [--out <path>] [--dry-run]`
- `roundtrip <sql_file> [obfuscation options] [--diff-report]`
- `workspace-info --workspace <dir>`

### 4.3 Common Obfuscation Options
- `--workspace <dir>` default: `<input_stem>.obf`
- `--dialect <name>` default: `tsql`
- `--seed <int>` deterministic mapping seed
- `--pretty/--no-pretty` default pretty enabled
- `--strict-go` accepted but currently no-op
- `--instruction-template <path>` custom `llm_instructions.md` content

### 4.4 Exit Codes
- `0`: success
- `1`: any handled application error (`InputFileError`, `ParseScriptError`, `WorkspaceError`), or deobfuscation dry-run with unresolved identifiers, or roundtrip unresolved identifiers

### 4.5 Output Behavior
- `obfuscate`:
  - prints obfuscated SQL to stdout
  - writes sibling output `<input_stem>_obfuscated<ext>`
  - writes workspace artifacts
- `deobfuscate` (non-dry-run):
  - prints deobfuscated SQL
  - writes deobfuscated SQL and reports
- `deobfuscate --dry-run`:
  - prints summary only
  - writes no deobfuscation output/report files
  - returns `1` if unknown or ambiguous mappings present
- `roundtrip`:
  - obfuscates, then deobfuscates obfuscated output
  - writes workspace + deobfuscation artifacts + roundtrip report
  - optionally writes diff report
  - returns `1` when deobfuscation report contains unknown or ambiguous identifiers
- `workspace-info`:
  - validates workspace/integrity and prints status lines

## 5. Batch Handling (`GO`)
- Split rule: lines matching `^\s*GO\s*$` (case-insensitive) are separators.
- Split keeps non-standalone `GO` text untouched.
- Join rule: batches joined by exact delimiter `\nGO\n`.

## 6. Obfuscation Semantics

### 6.1 Parser/Transformer Pipeline
- For each batch:
  - parse with `sqlglot.parse(batch, dialect=...)`
  - transform statements via AST walk (`Expression.transform(copy=True)`)
  - regenerate SQL as `stmt.sql(dialect=dialect, pretty=pretty)`
- Statement delimiter in generated batch: `;\n` between statements.
- Parse errors include batch index and SQL snippet context.

### 6.2 Identifier Normalization
- `normalize_identifier(raw)`:
  - trims
  - strips outer `[ ... ]` if present
  - extracts temp prefix:
    - `##` for global temp
    - `#` for temp
  - lowercases normalized value
- Mapping key is tuple `(normalized_value, temp_prefix)`.

### 6.3 Generated Names
- Source pool: `identifier_replacements.txt` (animal names)
- Randomization: `random.Random(seed)` shuffle
- Constraints:
  - must match regex `^[A-Za-z_][A-Za-z0-9_]*$`
  - must not be in T-SQL reserved keywords list
- Exhaustion fallback:
  - choose safe base and append numeric suffix (`lion2`, `lion3`, ...), guaranteeing uniqueness and safety

### 6.4 AST Rename Rules
- `Table`: rename table identifier as `kind=table`, except special case below
- `UPDATE alias target`: if `UPDATE <table_token>` matches any alias in same update statement, treat as alias (`kind=alias`, role `update_target_alias`)
- `Column`:
  - rename column identifier (`kind=column`)
  - rename qualifier identifier (`kind=alias`)
- `CTE`: rename CTE alias name (`kind=cte`)
- `TableAlias`:
  - rename alias identifier (`kind=alias`), except CTE declaration aliases (handled in CTE rule)
  - rename alias column list (`kind=column_alias`)
- `Alias` expression (`... AS X`): rename alias identifier (`kind=column_alias`)
- `ColumnDef`: rename column name (`kind=column_def`)
- `Schema` when used as insert target (`Insert.this`): rename listed identifiers (`kind=insert_column`)

### 6.5 Explicit Non-Renames (by behavior/tests)
- SQL keywords
- string/numeric literals
- variables (`@Var`)
- function names (e.g., `ABS`)
- schema qualifiers (e.g., `dbo`, `sales`)

## 7. Mapping and Context Payloads

### 7.1 Mapping Payload (`schema_version=1`)
- Root fields:
  - `schema_version`
  - `entries[]`
  - `forward_index`
  - `reverse_index`
- Each entry stores:
  - normalized and original lexemes
  - whether original was bracketed
  - obfuscated forms
  - `occurrences[]` with:
    - `kind`, `batch_index`, `statement_index`, `scope_id`, `parent_kind`, `role`
- `forward_index` maps normalized originals -> obfuscated lexeme
- `reverse_index` maps obfuscated lexeme -> normalized original metadata

### 7.2 Context Payload (`schema_version=1`)
- Includes:
  - `input_file`
  - `dialect`
  - `seed`
  - `pretty`
  - `batch_count`
  - `statement_count`
  - `mapping_entry_count`

## 8. Workspace Model

### 8.1 Default Path
- `<input_stem>.obf` in same directory as input SQL file.

### 8.2 Written Artifacts (obfuscate)
- `original.sql`
- `obfuscated.sql`
- `llm_instructions.md` (default or template override)
- `mapping.json`
- `context.json`
- `integrity.json`
- `mapping.schema.json`
- `context.schema.json`
- `integrity.schema.json`

### 8.3 Integrity Enforcement
- `integrity.json` format:
  - `schema_version=1`
  - `algorithm="sha256"`
  - `files` map
- Tracked files:
  - `original.sql`
  - `obfuscated.sql`
  - `mapping.json`
  - `context.json`
- On validation:
  - missing tracked file => error
  - checksum mismatch => error
  - unsupported algorithm => error
- Integrity checked by `deobfuscate`, `roundtrip`, and `workspace-info`.

### 8.4 Additional Artifacts (deobfuscate/roundtrip)
- `deobfuscated.sql`
- `reports/deobfuscation_report.json`
- `reports/coverage_report.txt`
- `reports/roundtrip_report.json` (roundtrip only)
- `reports/roundtrip_diff.txt` (when `--diff-report`)

## 9. Deobfuscation Semantics

### 9.1 Reverse Resolution Strategy
- Build reverse map keyed by obfuscated lexeme.
- Resolve candidate by:
  1. direct unique obfuscated match
  2. disambiguate by `kind`
  3. disambiguate by same `batch_index` + `statement_index`
- If unresolved:
  - no candidates => record unknown
  - multiple candidates => record ambiguous

### 9.2 AST Application Rules
- Mirrors obfuscation rule coverage (`Table`, `Column`, `CTE`, `TableAlias`, `Alias`, `ColumnDef`, insert `Schema`)
- Restores original bracket quoting when `original_was_bracketed` is true.

### 9.3 Report Payload
- Fields:
  - `mapped_identifiers`
  - `unknown_identifiers[]`
  - `ambiguous_identifiers[]`
  - `batch_count`
  - `statement_count`
  - `unknown_count`
  - `ambiguous_count`
  - `unknown_by_kind`
  - `ambiguous_by_kind`
  - `recommendations[]`
- Recommendation text behavior:
  - unknowns present -> message about introduced/renamed identifiers
  - ambiguous present -> message about alias/table structure drift
  - none present -> "No unresolved identifiers detected."

## 10. Errors
- Domain exceptions:
  - `ObfuscatorError` (base)
  - `InputFileError`
  - `ParseScriptError`
  - `WorkspaceError`
- CLI catches application errors and prints `Error: ...` to stderr, returns `1`.

## 11. Sample SQL Fixtures (Required)
The following files are part of the current fixture corpus and should be recreated exactly.

### `sample_sql/01_simple_select.sql`
```sql
-- Simple SELECT statement with WHERE clause
SELECT UserId, UserName, EmailAddress, CreatedDate
FROM Users
WHERE Status = 'Active'
  AND CreatedDate >= '2025-01-01'
ORDER BY CreatedDate DESC;
```

### `sample_sql/02_joins.sql`
```sql
-- SELECT with INNER JOIN and LEFT JOIN
SELECT 
    u.UserId,
    u.UserName,
    o.OrderId,
    o.OrderTotal,
    p.ProductName,
    od.Quantity
FROM Users u
INNER JOIN Orders o ON u.UserId = o.UserId
LEFT JOIN OrderDetails od ON o.OrderId = od.OrderId
LEFT JOIN Products p ON od.ProductId = p.ProductId
WHERE o.OrderDate >= '2025-06-01'
  AND u.Status = 'Active'
ORDER BY o.OrderDate DESC;
```

### `sample_sql/03_cte_example.sql`
```sql
-- CTE (Common Table Expression) example
WITH CustomerOrders AS (
    SELECT 
        UserId,
        COUNT(*) AS OrderCount,
        SUM(OrderTotal) AS TotalAmount
    FROM Orders
    GROUP BY UserId
),
TopCustomers AS (
    SELECT 
        UserId,
        OrderCount,
        TotalAmount,
        ROW_NUMBER() OVER (ORDER BY TotalAmount DESC) AS Rank
    FROM CustomerOrders
    WHERE OrderCount >= 3
)
SELECT 
    u.UserName,
    u.EmailAddress,
    tc.OrderCount,
    tc.TotalAmount,
    tc.Rank
FROM TopCustomers tc
INNER JOIN Users u ON tc.UserId = u.UserId
WHERE tc.Rank <= 10;
```

### `sample_sql/04_temporary_tables.sql`
```sql
-- Temporary table example
CREATE TABLE #TempOrders
(
  OrderId INT,
  UserId INT,
  OrderDate DATE,
  OrderTotal DECIMAL(10, 2),
  Status VARCHAR(50)
);

INSERT INTO #TempOrders
  (OrderId, UserId, OrderDate, OrderTotal, Status)
SELECT OrderId, UserId, OrderDate, OrderTotal, Status
FROM Orders
WHERE OrderDate >= '2025-01-01';

SELECT
  u.UserName,
  COUNT(*) AS OrderCount,
  AVG(t.OrderTotal) AS AvgOrderAmount
FROM #TempOrders t
  INNER JOIN Users u ON t.UserId = u.UserId
WHERE t.Status = 'Completed'
GROUP BY u.UserName
HAVING COUNT(*) > 2
ORDER BY AvgOrderAmount DESC;

DROP TABLE #TempOrders;
```

### `sample_sql/05_dml_operations.sql`
```sql
-- INSERT, UPDATE, and DELETE statements
INSERT INTO Users (UserId, UserName, EmailAddress, Status, CreatedDate)
VALUES (1001, 'JohnDoe', 'john@example.com', 'Active', '2025-02-14');

UPDATE Users
SET LastLoginDate = GETDATE(),
    Status = 'Active'
WHERE UserId = 1001;

DELETE FROM Orders
WHERE OrderDate < '2020-01-01'
  AND Status = 'Cancelled';

INSERT INTO AuditLog (UserId, Action, ActionDate, OldValue, NewValue)
SELECT 
    UserId,
    'StatusChange',
    GETDATE(),
    'Inactive',
    'Active'
FROM Users
WHERE Status = 'Active'
  AND LastLoginDate > DATEADD(DAY, -30, GETDATE());
```

### `sample_sql/06_aggregate_functions.sql`
```sql
-- Aggregate functions and GROUP BY
SELECT 
    u.UserName,
    u.City,
    COUNT(DISTINCT o.OrderId) AS TotalOrders,
    SUM(o.OrderTotal) AS TotalAmount,
    AVG(o.OrderTotal) AS AvgOrderAmount,
    MIN(o.OrderDate) AS FirstOrderDate,
    MAX(o.OrderDate) AS LastOrderDate
FROM Users u
LEFT JOIN Orders o ON u.UserId = o.UserId
WHERE u.Status = 'Active'
  AND o.OrderDate >= '2024-01-01'
GROUP BY u.UserId, u.UserName, u.City
HAVING COUNT(DISTINCT o.OrderId) >= 5
ORDER BY TotalAmount DESC;
```

### `sample_sql/07_multiple_batches.sql`
```sql
-- Multiple batches with GO separators

-- Batch 1: Create a temporary table and populate it
CREATE TABLE #SalesData
(
  SalesId INT,
  SalesDate DATE,
  Amount DECIMAL(10, 2),
  Region VARCHAR(50)
);

INSERT INTO #SalesData
  (SalesId, SalesDate, Amount, Region)
SELECT
  OrderId,
  OrderDate,
  OrderTotal,
  Region
FROM Orders
WHERE OrderDate >= DATEADD(MONTH, -3, GETDATE());

GO

-- Batch 2: Query the temporary table
SELECT
  Region,
  COUNT(*) AS SalesCount,
  SUM(Amount) AS TotalAmount,
  AVG(Amount) AS AvgAmount
FROM #SalesData
GROUP BY Region
ORDER BY TotalAmount DESC;

GO

-- Batch 3: Update and cleanup
UPDATE #SalesData
SET Region = 'Other'
WHERE Region IS NULL;

SELECT *
FROM #SalesData
WHERE Region = 'Other';

DROP TABLE #SalesData;
```

### `sample_sql/08_schema_qualified.sql`
```sql
-- Schema-qualified tables and subqueries
SELECT 
    u.UserId,
    u.UserName,
    dbo.Users.EmailAddress,
    (SELECT COUNT(*) 
     FROM dbo.Orders o 
     WHERE o.UserId = u.UserId) AS OrderCount,
    (SELECT SUM(OrderTotal) 
     FROM dbo.Orders o2 
     WHERE o2.UserId = u.UserId) AS TotalSpent
FROM dbo.Users u
WHERE u.UserId IN (
    SELECT DISTINCT o.UserId
    FROM dbo.Orders o
    WHERE o.OrderDate >= '2025-01-01'
      AND o.OrderTotal > 100
)
  AND u.Status = 'Active'
ORDER BY TotalSpent DESC;
```

Note: `sample_sql/06_aggregate_functions_obfuscated.sql` is not present in the current repository contents.

## 12. Test Suite Requirements (Acceptance Criteria)
Recreated app should satisfy behavior represented by these test files:

- `tests/test_cli.py`
  - legacy mode and subcommands work
  - output/workspace files are created correctly
  - parse errors return non-zero and include batch context
  - pretty vs no-pretty formatting behavior
  - custom workspace path support
  - deobfuscate dry-run semantics
  - roundtrip and diff report generation
  - custom instruction template support
  - workspace-info output includes expected status lines
  - integrity tampering is detected and fails

- `tests/test_pipeline.py`
  - parse errors with batch context and SQL snippet
  - multi-batch valid scripts pass
  - pretty default true; no-pretty compact

- `tests/test_transformer.py`
  - table/column/alias/CTE/temp table renames happen
  - schema qualifier preserved
  - update alias target logic works
  - literals/variables/functions/keywords unaffected

- `tests/test_registry.py`
  - normalization behavior (brackets/case/temp prefixes)
  - deterministic seeded mapping
  - mapping payload includes forward/reverse indexes and occurrences

- `tests/test_names.py`
  - reserved/invalid names skipped
  - suffix fallback used safely
  - runtime error when no safe candidate exists

- `tests/test_go_batches.py`
  - split/join GO roundtrip behavior
  - case-insensitive GO separators

- `tests/test_workspace.py`
  - default workspace path format
  - mapping/context validation errors on bad schema/shape

- `tests/test_deobfuscation.py`
  - obfuscate->deobfuscate roundtrip restores key identifiers
  - unknown identifiers are reported with recommendations

- `tests/test_identifier_safety.py`
  - bracketing/safety helper behavior
  - parseability of obfuscated outputs across SQL patterns
  - generated names are safe and deterministic with seeds
  - schema-qualified names valid and schema tokens preserved

- `tests/test_llm_workflow_integration.py`
  - realistic edited obfuscated SQL deobfuscates cleanly
  - dry-run for edited multi-batch scripts
  - same seed gives identical artifacts and output
  - different seeds change mappings/output

- `tests/test_suite_coverage.py`
  - expanded positive/negative/determinism/complex-scenario checks

- `tests/test_final_validation.py`
  - end-to-end smoke scenarios
  - exit-code correctness
  - parseability and complex real-world script handling

## 13. Rebuild Guidance (Parity Targets)
- Keep schema versions at `1` for mapping/context/integrity.
- Preserve exact tracked integrity files and checksum algorithm (`sha256`).
- Preserve deobfuscation report field names and dry-run stdout summary labels.
- Preserve command names, flags, defaults, and legacy mode dispatch behavior.
- Preserve GO splitting rules and `\nGO\n` joining behavior.
- Preserve deterministic output characteristics for same seed input.

## 14. Minimal Dependency/Build Metadata
- `pyproject.toml` project name/version: `sql-obfuscator` / `0.1.0`
- Build backend: setuptools
- Runtime dependency declared in pyproject: `sqlglot>=26.0.0`
- Runtime pin in requirements: `sqlglot>=28,<29`
- Dev extras include pytest.
