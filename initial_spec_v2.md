# SQL Identifier Obfuscator (Animal Mapper) - Specification v2

## 1. Purpose
Build a Python CLI tool that reads a T-SQL script (`.sql`) and writes an obfuscated but syntactically valid T-SQL script to `stdout`.

Obfuscation target:
- Table names
- Column names
- CTE names
- Temp table names

Obfuscation style:
- Replace identifiers with generated animal-based names such as `lion`, `cat`, `dog`, `monkey`.

Primary guarantee:
- Output is syntactically valid SQL for the configured dialect (`tsql`), assuming corresponding schema objects exist.

## 2. Scope

### 2.1 In Scope
- CLI execution: `python obfuscator.py <path-to-file.sql>`
- File loading and parse error handling
- AST-based transformation using `sqlglot`
- Consistent identifier mapping within one run
- Output to `stdout`

### 2.2 Out of Scope (Non-Goals)
- Dynamic SQL inside string literals
- Database-aware semantic resolution
- Stored procedure/function parameter renaming
- Guaranteeing semantic equivalence
- Preserving original formatting beyond what parser/generator supports

## 3. CLI Contract

### 3.1 Usage
```bash
python obfuscator.py input.sql
```

### 3.2 Inputs
- Required positional argument: path to `.sql` file

### 3.3 Outputs
- On success: transformed SQL to `stdout`, exit code `0`
- On failure: human-readable error to `stderr`, non-zero exit code

### 3.4 Error Cases
- File not found
- File unreadable
- Parse failure
- Internal transformation failure

## 4. Parsing and Script Model

### 4.1 Multi-Statement Requirement
- Must support full scripts containing multiple SQL statements.
- Use `sqlglot.parse(..., dialect="tsql")`, not only `parse_one`.

### 4.2 Batch Separator Policy (`GO`)
- `GO` is a tooling batch separator, not a SQL statement.
- Required behavior:
1. Split script into batches on standalone `GO` lines (case-insensitive, optional surrounding whitespace).
2. Parse and transform each batch independently.
3. Reassemble output batches with `GO` separators preserved.

If `GO` handling is deferred, it must be documented as a known limitation and covered by a failing test marked `xfail` (or equivalent).

## 5. Identifier Obfuscation Rules

## 5.1 Replace
- Table names in `FROM`, `JOIN`, DML targets, and DDL targets
- Column names in projections, predicates, definitions, and insert column lists
- CTE names at declaration and reference sites
- Temp table names (`#local`, `##global`)

### 5.2 Do Not Replace
- SQL keywords
- String literals
- Numeric literals
- Schema/database qualifiers (`dbo`, `[dbo]`, etc.)
- Aliases (table aliases, CTE aliases, derived table aliases)
- Variable names (`@x`)
- Function names (built-in or user-defined invocation names)

### 5.3 Normalization
Normalization key for mapping:
1. Strip outer brackets if present (`[UserId]` -> `UserId`)
2. Preserve temp marker separately (`#` or `##`)
3. Compare case-insensitively (`lower()`)

Equivalent examples:
- `UserId`, `[UserId]`, `USERID` -> same logical key
- `#TempOrders`, `[#TempOrders]` -> same logical key with local-temp prefix
- `##TempOrders` remains distinct from `#TempOrders`

### 5.4 Mapping Scope
Default v2 policy: global per script run.
- Same normalized key always maps to same obfuscated identifier across the full input script.
- Consequence: `u.Id` and `o.Id` both map to same obfuscated column name.
- This is accepted by design for obfuscation consistency.

### 5.5 Obfuscated Name Generation
Generator requirements:
- Deterministic mode supported (seeded RNG or stable order assignment)
- Uniqueness across generated identifiers in a run
- Collision-safe with reserved words list

Fallback when animal pool is exhausted:
1. Use suffix strategy: `lion2`, `lion3`, etc.
2. Never emit duplicates

### 5.6 Identifier Safety
- Generated names must be valid T-SQL identifiers when emitted.
- If a generated token could be unsafe (reserved keyword or invalid shape), emit bracketed form.
- Preserve temp prefix:
- `#TempOrders` -> `#lion`
- `##TempOrders` -> `##lion`

## 6. AST Transformation Requirements

### 6.1 Implementation Approach
- Use `sqlglot` AST traversal/transformation (custom transformer/visitor).
- Transform only targeted identifier fields, not full node text.

### 6.2 Required Statement Coverage
- `SELECT` with joins, subqueries, predicates
- `WITH` (CTE declaration + references)
- `CREATE TABLE` (table + column definitions)
- `INSERT INTO` (target table + explicit column list)
- `UPDATE` and `DELETE` target/table references

### 6.3 Qualification Handling
- For qualified names (`dbo.Users`, `u.UserId`):
- Rename only the identifier component (`Users`, `UserId`)
- Keep qualifier unchanged (`dbo`, `u`)

## 7. Architecture
- CLI module
- SQL loader and batch splitter
- Parser layer (`sqlglot`, dialect `tsql`)
- Identifier registry (normalization + map storage)
- Name provider (animal generator + collision handling)
- AST transformer
- SQL emitter and output writer

## 8. Configuration
Minimal v2 configuration surface:
- `--dialect` (default: `tsql`)
- `--seed` (optional; enables deterministic mapping)
- `--strict-go` (optional; fail if `GO` cannot be safely handled)

If options are not implemented yet, keep them documented as planned flags and track as TODOs.

## 9. Testing Specification

### 9.1 Core Positive Tests
1. Simple select:
```sql
SELECT UserId FROM Users;
```
2. Join with repeated column names:
```sql
SELECT u.Id, o.Id FROM Users u JOIN Orders o ON u.Id = o.Id;
```
3. CTE declaration and reference:
```sql
WITH RecentOrders AS (SELECT * FROM Orders) SELECT * FROM RecentOrders;
```
4. Temp tables:
```sql
CREATE TABLE #TempOrders (UserId INT); SELECT * FROM #TempOrders;
CREATE TABLE ##GlobalTemp (UserId INT); SELECT * FROM ##GlobalTemp;
```
5. Create + insert:
```sql
CREATE TABLE Users (UserId INT, Name NVARCHAR(50));
INSERT INTO Users (UserId, Name) VALUES (1, 'A');
```
6. Mixed bracket/case normalization:
```sql
SELECT [UserId], USERID FROM [Users] WHERE UserId = 1;
```
7. Qualified names:
```sql
SELECT u.UserId FROM dbo.Users u;
```

### 9.2 Batch Tests (`GO`)
1. Multiple batches with standalone `GO`
2. Case-insensitive `go`
3. `GO` inside string literal should not be treated as separator when not standalone

### 9.3 Negative Tests
1. Missing file path
2. Invalid SQL parse error
3. Animal pool exhaustion path
4. Reserved keyword collision handling

### 9.4 Determinism Tests
1. Same input + same seed => identical output
2. Same input + different seed => different mapping (unless collisions force same names)

### 9.5 Acceptance Criteria
- Output parses successfully under `tsql` for each positive test
- Required non-renamed tokens remain unchanged
- Mapping consistency holds across full script
- CLI exit codes align with success/failure contract

## 10. Performance and Limits
- Target script size: up to at least 1 MB in normal runtime
- Time and memory scale with AST size
- Multi-GB SQL dumps are explicitly out of scope for v2

## 11. Known Limitations (Explicit)
- No dynamic SQL rewriting
- No semantic disambiguation by schema/object metadata
- Formatting may differ from original source after generation

## 12. Delivery Checklist
- `obfuscator.py` CLI entrypoint
- Identifier registry with normalization rules
- Animal provider with collision-safe generation
- AST transformer covering required statements
- Test suite covering sections 9.1-9.5
- README usage and limitation notes
