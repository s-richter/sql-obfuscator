# SQL Identifier Obfuscator

Python CLI tool for obfuscating SQL identifiers (table names, column names, CTE names, temp tables) in T-SQL scripts using an AST-based workflow.

## Features

- Deterministic obfuscation: same seed produces identical output
- Batch processing: handles SQL scripts with standalone `GO` separators
- Reserved keyword safety: generated names never collide with T-SQL keywords
- Syntactic preservation: transformed output remains parseable T-SQL
- Comprehensive renaming:
  - Table names (including temp tables `#table` and global `##table`)
  - Column names in `SELECT`, `WHERE`, `JOIN`, `INSERT`, and column definitions
  - CTE (Common Table Expression) names
  - Preserves schema qualifiers (for example `dbo.`)
  - Obfuscates aliases and preserves variables
- Non-renaming guarantees:
  - SQL keywords
  - String/numeric literals
  - Variables (`@variable`)
  - Function invocation names

## Installation

```bash
pip install -e .
```

For development with testing:

```bash
pip install -e .[dev]
```

## Usage

### Basic Usage

```bash
python obfuscator.py script.sql
```

Output is printed to stdout. Redirects are supported:

```bash
python obfuscator.py input.sql > output.sql
```

### Configuration Flags

#### `--dialect` (default: `tsql`)

Specifies the SQL dialect for parsing.

```bash
python obfuscator.py script.sql --dialect tsql
```

#### `--seed` (optional)

Enables deterministic mode with a fixed random seed.

```bash
python obfuscator.py script.sql --seed 42
```

Useful for:

- Reproducible transformations
- Testing
- Consistent obfuscation across runs

#### `--strict-go` (optional)

Accepted by the CLI for future strict batch handling. Current implementation treats it as a no-op.

```bash
python obfuscator.py script.sql --strict-go
```

### Examples

#### Simple transform

```bash
python obfuscator.py users.sql
```

#### Deterministic output with seed

```bash
python obfuscator.py users.sql --seed 12345 > obfuscated.sql
```

#### Multiple runs with same seed

```bash
# Run 1
python obfuscator.py users.sql --seed 42 > run1.sql

# Run 2
python obfuscator.py users.sql --seed 42 > run2.sql

# run1.sql and run2.sql are identical
```

## How It Works

1. Parse: SQL script is parsed using `sqlglot` with the specified dialect.
2. Split: script is split on standalone `GO` statements.
3. Transform: each batch is transformed via AST visitor:
   - Identifies identifier nodes (table, column, CTE names)
   - Looks up or generates replacement animal-based names
   - Replaces identifiers in the AST
4. Emit: transformed SQL is written to stdout with `GO` separators preserved.

Note: parseability of transformed output is covered by automated tests, not by an extra final parse pass in the runtime pipeline.

## Identifier Replacement Strategy

Names are generated from a list of animal names (for example `shark`, `dolphin`, `eagle`). Names are:

- Unique within a script run
- Deterministic when using `--seed`
- Safe for T-SQL (no reserved keywords)
- Unambiguous (same normalized identifier maps to the same replacement)

When the base animal pool is exhausted, suffixed fallback names are generated (for example `lion2`, `lion3`) while still enforcing identifier safety.

### Case and Bracket Normalization

Identifiers in SQL Server are case-insensitive and can be bracketed. The obfuscator:

- Normalizes to lowercase for mapping (`UserId`, `userid`, `USERID` map together)
- Handles bracketed identifiers correctly
- Preserves temp table prefixes (`#` / `##`)

### Example

Input:

```sql
SELECT UserId, UserName FROM Users WHERE Status = 'Active';
```

Output (example with `seed=42`):

```sql
SELECT shark, dolphin FROM tiger WHERE eagle = 'Active';
```

String literal `'Active'` is unchanged.

## Known Limitations

1. Non-standalone `GO`: text such as `GoTable` or `GOING_CONCERN` is not treated as a batch separator.
2. Dynamic SQL: string literals containing SQL code are not parsed or transformed.

   ```sql
   EXEC sp_executesql N'SELECT * FROM Users';  -- Users will not be renamed inside the string
   ```

3. Comments: comment text is not transformed.
4. Semantic equivalence: obfuscation targets syntactic validity, not semantic meaning.
5. Formatting: `sqlglot` may normalize SQL formatting/comments during output.

## Guarantee Boundaries

### What Is Guaranteed

- Output is valid, parseable T-SQL for successfully transformed batches.
- No reserved keywords are generated as identifiers.
- Same seed produces identical output.
- Table, column, and CTE identifiers targeted by the transformer are renamed consistently.
- Schema qualifiers are preserved.
- Variables, keywords, and string literals are unchanged.
- Batch structure (`GO` separators) is preserved.

### What Is Not Guaranteed

- Semantic equivalence for all SQL workloads
- Performance equivalence (execution plans may differ)
- Application-specific logic relying on identifier names

## Error Handling

Errors are printed to stderr with context. Exit code is `1` on error, `0` on success.

### Error Examples

Missing file:

```text
$ python obfuscator.py nonexistent.sql
Error: Input file not found: nonexistent.sql
```

Parse error:

```text
$ python obfuscator.py broken.sql
Error: Parse error in batch 2/3:
  Error: Required keyword: 'this' missing for...
  SQL: SELECT ((
```

## Development

### Running Tests

```bash
pytest                          # All tests
pytest -v                       # Verbose
pytest tests/test_cli.py        # Specific file
pytest -k "test_determinism"    # Matching pattern
```

### Project Structure

```text
sql-obfuscator/
|-- src/sql_obfuscator/
|   |-- __init__.py
|   |-- cli.py                 # CLI entry point
|   |-- pipeline.py            # Main obfuscation pipeline
|   |-- transformer.py         # AST transformation logic
|   |-- registry.py            # Identifier mapping registry
|   |-- names.py               # Name generation and validation
|   |-- go_batches.py          # GO statement splitting
|   |-- errors.py              # Custom exception types
|   `-- *.txt                  # Data files (keywords, animals)
|-- tests/
|   |-- test_*.py
|   `-- conftest.py
`-- README.md
```

### Test Coverage

The current suite contains 70+ test functions across CLI, parsing/batches, transformation, identifier safety, determinism, and output parseability scenarios.

## License

See LICENSE file (if present).
