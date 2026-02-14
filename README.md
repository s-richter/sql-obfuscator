# SQL Identifier Obfuscator

Python CLI tool for obfuscating SQL identifiers (table names, column names, CTE names, temp tables) in T-SQL scripts using an AST-based workflow.

## Features

- **Deterministic obfuscation**: Same seed produces identical output for consistent results
- **Batch processing**: Handles SQL scripts with `GO` statement separators
- **Reserved keyword safety**: Generated names never collide with T-SQL keywords
- **Syntactic preservation**: Output remains parseable T-SQL
- **Comprehensive renaming**:
  - Table names (including temp tables `#table` and global `##table`)
  - Column names in SELECT, WHERE, JOIN, INSERT
  - CTE (Common Table Expression) names
  - Preserves schema qualifiers (e.g., `dbo.`)
  - Preserves aliases and variables
- **Non-renaming guarantees**:
  - SQL keywords
  - String/numeric literals
  - Variables (`@variable`)
  - Function invocation names
  - Aliases

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

Specifies the SQL dialect for parsing. Currently tested with `tsql` (SQL Server T-SQL).

```bash
python obfuscator.py script.sql --dialect tsql
```

#### `--seed` (optional)

Enables deterministic mode with a fixed random seed. Same seed always produces identical output.

```bash
python obfuscator.py script.sql --seed 42
```

Useful for:

- Reproducible transformations
- Testing
- Consistent obfuscation across runs

#### `--strict-go` (optional)

Enables strict batch handling mode. Reserved for future use (currently processing all batches).

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

1. **Parse**: SQL script is parsed using `sqlglot` with the specified dialect
2. **Split**: Script is split on standalone `GO` statements (batch separators)
3. **Transform**: Each batch is transformed via AST visitor:
   - Identifies all identifier nodes (table, column, CTE names)
   - Looks up or generates replacement animal-based names
   - Replaces identifiers in the AST
4. **Validate**: Output is verified to remain parseable
5. **Emit**: Transformed SQL is written to stdout with `GO` batch separators preserved

## Identifier Replacement Strategy

Names are generated from a list of animal names (e.g., `shark`, `dolphin`, `eagle`). Names are:

- **Unique** within a script run
- **Deterministic** when using `--seed`
- **Safe** for T-SQL (no reserved keywords)
- **Unambiguous** (same identifier always maps to same replacement)

### Case and Bracket Normalization

Identifiers in SQL Server are case-insensitive and can be bracketed. The obfuscator:

- Normalizes to lowercase for matching (so `UserId`, `userid`, `USERID` all map to the same replacement)
- Preserves brackets when output requires them (legacy or special characters)

### Example

Input:

```sql
SELECT UserId, UserName FROM Users WHERE Status = 'Active';
```

Output (example with seed=42):

```sql
SELECT shark, dolphin FROM tiger WHERE eagle = 'Active';
```

Note: String literal `'Active'` is unchanged.

## Known Limitations

1. **Non-standalone GO**: GO text that's part of identifiers (e.g., `GoTable`, `GOING_CONCERN`) is not treated as a batch separator.
2. **Alias Preservation**: Table and column aliases are preserved as-is. Only the underlying identifier is renamed.

3. **Dynamic SQL**: String literals containing SQL code are not parsed or transformed. E.g.:

   ```sql
   EXEC sp_executesql N'SELECT * FROM Users';  -- Users won't be renamed
   ```

4. **Comments**: SQL comments are preserved but identifier mentions within comments are not transformed.

5. **Semantic Equivalence**: Obfuscation preserves **syntactic** validity, not semantic meaning. Logic depending on identifier names (rare) would break.

## Guarantee Boundaries

### What is Guaranteed

- ✅ Output is valid, parseable T-SQL (same dialect as input)
- ✅ No reserved keywords are generated as identifiers
- ✅ Same seed produces identical output (deterministic)
- ✅ All table, column, and CTE names are renamed
- ✅ Schema qualifiers are preserved
- ✅ Variables, keywords, and string literals are unchanged
- ✅ Batch structure (GO separators) is preserved

### What is NOT Guaranteed

- ❌ Semantic equivalence (would be impossible to guarantee for all SQL)
- ❌ Performance (obfuscated queries may have different plans)
- ❌ Application-specific logic relying on identifier names
- ❌ Very large scripts hitting animal name pool limits (fallback names are used)

## Error Handling

Errors are printed to stderr with context. Exit code is 1 on error, 0 on success.

### Error Examples

**Missing file:**

```
$ python obfuscator.py nonexistent.sql
Error: Input file not found: nonexistent.sql
```

**Parse error:**

```
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

```
sql-obfuscator/
├── src/sql_obfuscator/
│   ├── __init__.py
│   ├── cli.py              # CLI entry point
│   ├── pipeline.py         # Main obfuscation pipeline
│   ├── transformer.py      # AST transformation logic
│   ├── registry.py         # Identifier mapping registry
│   ├── names.py            # Name generation and validation
│   ├── go_batches.py       # GO statement splitting
│   ├── errors.py           # Custom exception types
│   └── *.txt               # Data files (keywords, animals)
├── tests/
│   ├── test_*.py           # Test modules (63+ tests)
│   └── conftest.py         # Pytest fixtures
└── README.md               # This file
```

### Test Coverage

- 63 tests covering:
  - CLI argument parsing and error handling
  - Batch splitting and GO separator handling
  - Identifier name generation and collision prevention
  - AST transformation correctness
  - Parser error reporting with context
  - Output parseability verification
  - Deterministic behavior with seeds

## License

See LICENSE file (if present).
