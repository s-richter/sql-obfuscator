# TASKS - SQL Identifier Obfuscator

This checklist is derived from `initial_spec_v2.md`.

## 1. Project Setup

- [x] Create package/module layout (`obfuscator.py` plus supporting modules)
- [x] Add dependency setup for `sqlglot`
- [x] Add basic `README` scaffold with usage placeholder

## 2. CLI Implementation

- [x] Implement CLI entrypoint: `python obfuscator.py <path-to-file.sql>`
- [x] Add argument parsing with `argparse`
- [x] Add planned flags:
- [x] `--dialect` (default `tsql`)
- [x] `--seed` (optional deterministic mode)
- [x] `--strict-go` (optional strict batch behavior)
- [x] Validate input path exists and is readable
- [x] Print transformed SQL to `stdout` on success
- [x] Print errors to `stderr` and return non-zero exit code on failure

## 3. Batch Handling (`GO`)

- [x] Implement splitter for standalone `GO` lines (case-insensitive)
- [x] Ensure surrounding whitespace is handled
- [x] Ensure non-standalone `GO` text is not treated as separator
- [x] Reassemble transformed batches with `GO` preserved
- [ ] Support strict mode behavior for `--strict-go` (fail fast on unsupported cases)

## 4. Identifier Registry

- [x] Create centralized identifier mapping registry
- [x] Implement normalization:
- [x] Strip outer brackets
- [x] Case-insensitive keying
- [x] Preserve temp prefix metadata (`#` vs `##`)
- [x] Enforce global-per-script mapping scope
- [x] Provide API for lookup-or-create behavior

## 5. Animal Name Provider

- [x] Add base animal word list
- [x] Generate unique names per run
- [x] Implement deterministic mode when `--seed` is provided
- [x] Add exhaustion fallback (`name2`, `name3`, ...)
- [x] Add reserved-keyword/invalid-identifier safety checks
- [x] Ensure generated names are safe for T-SQL output

## 6. AST Parsing and Emission

- [x] Parse each batch using `sqlglot` with selected dialect
- [x] Add robust parse error handling with context
- [x] Emit transformed SQL text for each batch
- [x] Ensure final output is assembled in script order

## 7. AST Transformation Rules

- [x] Implement transformer/visitor for targeted identifier fields only
- [x] Rename table names in DML/DDL targets and references
- [x] Rename column names in projections, predicates, definitions, insert lists
- [x] Rename CTE names at declaration and reference sites
- [x] Rename temp table names while preserving `#` or `##`
- [x] Preserve schema/database qualifiers (e.g., `dbo`)
- [x] Preserve aliases (table, CTE, derived table aliases)
- [x] Do not rename:
- [x] SQL keywords
- [x] String/numeric literals
- [x] Variables (`@...`)
- [x] Function invocation names

## 8. Identifier Safety and Output Correctness

- [x] Handle reserved keyword collisions
- [x] Bracket generated names when needed for syntactic safety
- [x] Keep syntactic validity under `tsql`
- [x] Verify output remains parseable after transformation

## 9. Test Suite

- [x] Add test harness (e.g., `pytest`)
- [x] Add positive tests:
- [x] Simple `SELECT`
- [x] `JOIN` with repeated column names
- [x] CTE declaration + reference
- [x] Temp tables (`#` and `##`)
- [x] `CREATE TABLE` + `INSERT`
- [x] Mixed bracket/case normalization
- [x] Qualified names (`dbo.Users`, `u.UserId`)
- [x] Add `GO` batch tests:
- [x] Multiple batches
- [x] Lowercase `go`
- [x] Non-standalone `GO` text
- [x] Add negative tests:
- [x] Missing file
- [x] Parse error
- [x] Animal pool exhaustion behavior
- [x] Reserved keyword collision behavior
- [x] Add determinism tests:
- [x] Same seed => same output
- [x] Different seed => mapping differs
- [x] Add assertions for exit codes and stderr/stdout behavior

## 10. Documentation

- [x] Document CLI usage examples
- [x] Document configuration flags and defaults
- [x] Document known limitations
- [x] Document guarantee boundaries (syntactic validity, not semantic equivalence)

## 11. Final Validation

- [x] Run full test suite and ensure green
- [x] Run manual smoke test on multi-statement sample with `GO`
- [x] Verify no unintended alias/schema renaming occurs
- [x] Confirm deterministic output with fixed seed
- [x] Confirm failure modes return non-zero exit code
