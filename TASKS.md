# TASKS - SQL Identifier Obfuscator

This checklist is derived from `initial_spec_v2.md`.

## 1. Project Setup
- [ ] Create package/module layout (`obfuscator.py` plus supporting modules)
- [ ] Add dependency setup for `sqlglot`
- [ ] Add basic `README` scaffold with usage placeholder

## 2. CLI Implementation
- [ ] Implement CLI entrypoint: `python obfuscator.py <path-to-file.sql>`
- [ ] Add argument parsing with `argparse`
- [ ] Add planned flags:
- [ ] `--dialect` (default `tsql`)
- [ ] `--seed` (optional deterministic mode)
- [ ] `--strict-go` (optional strict batch behavior)
- [ ] Validate input path exists and is readable
- [ ] Print transformed SQL to `stdout` on success
- [ ] Print errors to `stderr` and return non-zero exit code on failure

## 3. Batch Handling (`GO`)
- [ ] Implement splitter for standalone `GO` lines (case-insensitive)
- [ ] Ensure surrounding whitespace is handled
- [ ] Ensure non-standalone `GO` text is not treated as separator
- [ ] Reassemble transformed batches with `GO` preserved
- [ ] Support strict mode behavior for `--strict-go` (fail fast on unsupported cases)

## 4. Identifier Registry
- [ ] Create centralized identifier mapping registry
- [ ] Implement normalization:
- [ ] Strip outer brackets
- [ ] Case-insensitive keying
- [ ] Preserve temp prefix metadata (`#` vs `##`)
- [ ] Enforce global-per-script mapping scope
- [ ] Provide API for lookup-or-create behavior

## 5. Animal Name Provider
- [ ] Add base animal word list
- [ ] Generate unique names per run
- [ ] Implement deterministic mode when `--seed` is provided
- [ ] Add exhaustion fallback (`name2`, `name3`, ...)
- [ ] Add reserved-keyword/invalid-identifier safety checks
- [ ] Ensure generated names are safe for T-SQL output

## 6. AST Parsing and Emission
- [ ] Parse each batch using `sqlglot` with selected dialect
- [ ] Add robust parse error handling with context
- [ ] Emit transformed SQL text for each batch
- [ ] Ensure final output is assembled in script order

## 7. AST Transformation Rules
- [ ] Implement transformer/visitor for targeted identifier fields only
- [ ] Rename table names in DML/DDL targets and references
- [ ] Rename column names in projections, predicates, definitions, insert lists
- [ ] Rename CTE names at declaration and reference sites
- [ ] Rename temp table names while preserving `#` or `##`
- [ ] Preserve schema/database qualifiers (e.g., `dbo`)
- [ ] Preserve aliases (table, CTE, derived table aliases)
- [ ] Do not rename:
- [ ] SQL keywords
- [ ] String/numeric literals
- [ ] Variables (`@...`)
- [ ] Function invocation names

## 8. Identifier Safety and Output Correctness
- [ ] Handle reserved keyword collisions
- [ ] Bracket generated names when needed for syntactic safety
- [ ] Keep syntactic validity under `tsql`
- [ ] Verify output remains parseable after transformation

## 9. Test Suite
- [ ] Add test harness (e.g., `pytest`)
- [ ] Add positive tests:
- [ ] Simple `SELECT`
- [ ] `JOIN` with repeated column names
- [ ] CTE declaration + reference
- [ ] Temp tables (`#` and `##`)
- [ ] `CREATE TABLE` + `INSERT`
- [ ] Mixed bracket/case normalization
- [ ] Qualified names (`dbo.Users`, `u.UserId`)
- [ ] Add `GO` batch tests:
- [ ] Multiple batches
- [ ] Lowercase `go`
- [ ] Non-standalone `GO` text
- [ ] Add negative tests:
- [ ] Missing file
- [ ] Parse error
- [ ] Animal pool exhaustion behavior
- [ ] Reserved keyword collision behavior
- [ ] Add determinism tests:
- [ ] Same seed => same output
- [ ] Different seed => mapping differs
- [ ] Add assertions for exit codes and stderr/stdout behavior

## 10. Documentation
- [ ] Document CLI usage examples
- [ ] Document configuration flags and defaults
- [ ] Document known limitations
- [ ] Document guarantee boundaries (syntactic validity, not semantic equivalence)

## 11. Final Validation
- [ ] Run full test suite and ensure green
- [ ] Run manual smoke test on multi-statement sample with `GO`
- [ ] Verify no unintended alias/schema renaming occurs
- [ ] Confirm deterministic output with fixed seed
- [ ] Confirm failure modes return non-zero exit code
