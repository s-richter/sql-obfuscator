# Multi-Dialect SQL Obfuscator Migration Backlog (T-SQL + Hive)

## Purpose
This document captures the implementation backlog for evolving `sql-obfuscator` from a primarily T-SQL-focused tool into a dialect-aware architecture with first-class Hive SQL (Cloudera) support.

## Current Constraints Identified
1. Dialect flag exists, but behavior is still T-SQL-biased in core modules.
2. `GO` batch splitting is unconditional, which is incorrect for Hive.
3. Identifier safety checks are tied to T-SQL reserved keywords.
4. Bracket-quote assumptions (`[name]`) are embedded in normalization and deobfuscation.
5. Tests and documentation are predominantly T-SQL-specific and do not protect Hive behavior.

## Target Definition for "Generic + Hive-ready"
1. Parse and emit SQL according to selected dialect (`tsql`, `hive`, extensible later).
2. Apply dialect-aware batch separation rules (`GO` only where valid).
3. Apply dialect-aware identifier normalization and quoting restoration.
4. Apply dialect-aware reserved keyword safety.
5. Preserve reversibility (obfuscate/deobfuscate) under each dialect.
6. Persist dialect strategy metadata in workspace artifacts for reliable reverse mapping.

## Recommended Architecture
1. Introduce a `DialectProfile` strategy abstraction.
2. Move dialect-sensitive rules behind profile APIs:
   - `split_batches(script)`
   - `join_batches(batches)`
   - `normalize_identifier(raw)`
   - `is_safe_identifier(name)`
   - `apply_original_quoting(identifier_node, metadata)`
3. Keep current behavior as `TsqlProfile` (parity first), then add `HiveProfile`.

## Execution Sequence (Recommended)
1. `ARCH-001`
2. `DIALECT-TSQL-001`
3. `PIPELINE-001`
4. `SCHEMA-001`
5. `NAMES-001`
6. `DIALECT-HIVE-001`
7. `TEST-TSQL-001`
8. `TEST-HIVE-001`
9. `FIXTURES-001`
10. `CLI-001`
11. `DOC-001`
12. `QA-001`

---

## Issue Backlog

### ARCH-001 Create Dialect Abstraction Layer
**Goal**: Remove hardcoded T-SQL assumptions from core flow.

**Scope**
1. Add `src/sql_obfuscator/dialects/base.py` with `DialectProfile` interface.
2. Add `src/sql_obfuscator/dialects/factory.py` to resolve profile from CLI `--dialect`.
3. Move dialect behavior contracts into profile methods:
   - `split_batches`
   - `join_batches`
   - `normalize_identifier`
   - `is_safe_identifier`
   - `apply_original_quoting`

**Acceptance Criteria**
1. Pipeline and deobfuscation are wired only through profile APIs.
2. Unknown dialect values produce clear user-facing errors.
3. Existing T-SQL tests pass unchanged.

---

### DIALECT-TSQL-001 Implement `TsqlProfile` (Parity Mode)
**Goal**: Preserve current behavior exactly under `--dialect tsql`.

**Scope**
1. Add `src/sql_obfuscator/dialects/tsql.py`.
2. Implement current `GO` split/join behavior.
3. Implement bracket-based normalization and re-quoting semantics.
4. Implement T-SQL keyword safety checks using existing keyword file.

**Acceptance Criteria**
1. No observable behavior change for existing T-SQL workflows.
2. All existing tests pass.
3. CLI default remains `tsql`.

---

### DIALECT-HIVE-001 Implement `HiveProfile` (MVP)
**Goal**: Add first-class Hive dialect strategy.

**Scope**
1. Add `src/sql_obfuscator/dialects/hive.py`.
2. Implement no-`GO` batch splitting (single-batch policy for MVP).
3. Implement Hive identifier normalization and quote handling (backticks).
4. Add Hive reserved keyword list and wire into safety checks.

**Acceptance Criteria**
1. `--dialect hive` obfuscates and deobfuscates simple scripts successfully.
2. Output parses with `sqlglot` using `dialect="hive"`.
3. T-SQL `GO` handling is not applied in Hive mode.

---

### PIPELINE-001 Refactor Pipeline/Deobfuscation to Use Profile
**Goal**: Centralize dialect-sensitive behavior.

**Scope**
1. Update `src/sql_obfuscator/pipeline.py` to use profile for batch and normalization operations.
2. Update `src/sql_obfuscator/deobfuscation.py` similarly.
3. Remove direct coupling to T-SQL-specific helpers where possible.

**Acceptance Criteria**
1. Core modules do not assume T-SQL behavior directly.
2. End-to-end obfuscate/deobfuscate works for both `tsql` and `hive` paths.
3. Parse/deobfuscation errors still include batch context.

---

### SCHEMA-001 Evolve Mapping/Context Schema for Multi-dialect Quoting
**Goal**: Store dialect-neutral quote metadata while preserving reversibility.

**Scope**
1. Replace `original_was_bracketed` with generic quote metadata fields.
2. Bump mapping/context schema versions as required.
3. Update schema validation in `src/sql_obfuscator/workspace.py`.
4. Define compatibility strategy for older workspaces.

**Acceptance Criteria**
1. Deobfuscation restores original quote style for both T-SQL and Hive.
2. Workspace validation enforces new schema.
3. Version mismatch errors are explicit and actionable.

---

### NAMES-001 Make Name Safety Dialect-aware
**Goal**: Remove hard dependency on T-SQL keyword logic.

**Scope**
1. Refactor `src/sql_obfuscator/names.py` so safety checks are profile-driven.
2. Keep deterministic generation and suffix fallback behavior unchanged.
3. Add tests for safe-name generation per dialect.

**Acceptance Criteria**
1. Generated names avoid reserved words in both dialects.
2. Deterministic seed behavior remains unchanged.
3. Shared flow no longer directly depends on `TSQL_RESERVED_KEYWORDS`.

---

### TEST-TSQL-001 Lock T-SQL Regression Suite
**Goal**: Prevent regressions while refactoring.

**Scope**
1. Mark or parameterize existing tests as T-SQL-specific where appropriate.
2. Preserve current assertions and behavior expectations for `tsql`.

**Acceptance Criteria**
1. Existing suite passes with default `tsql`.
2. T-SQL assumptions are explicit in tests.
3. No weakening of regression assertions.

---

### TEST-HIVE-001 Add Hive Unit/Integration Coverage
**Goal**: Build confidence in Hive support.

**Scope**
1. Add Hive tests for basic SELECT/JOIN/CTE obfuscation.
2. Add Hive deobfuscation tests for backtick quote restoration.
3. Add tests confirming no `GO` splitting in Hive mode.
4. Add dry-run and roundtrip tests for Hive workspace flow.

**Acceptance Criteria**
1. Hive outputs parse with `sqlglot` `dialect="hive"`.
2. Unknown/ambiguous reporting works in Hive mode.
3. Roundtrip passes for representative Hive fixtures.

---

### FIXTURES-001 Add Hive Sample SQL Corpus
**Goal**: Provide realistic Hive fixtures and examples.

**Scope**
1. Add `sample_sql/hive/` fixtures covering:
   - SELECT/JOIN
   - CTE
   - INSERT OVERWRITE
   - partition usage
   - alias-heavy scripts
2. Ensure fixtures reflect Cloudera-style Hive syntax.

**Acceptance Criteria**
1. Fixtures parse with `sqlglot` Hive dialect.
2. At least one fixture covers advanced Hive syntax beyond simple ANSI patterns.
3. Fixtures are referenced by tests/docs.

---

### CLI-001 Improve CLI Dialect UX and Validation
**Goal**: Make dialect behavior explicit and predictable.

**Scope**
1. Update CLI help/description to reflect multi-dialect behavior.
2. Validate `--dialect` against supported profile registry.
3. Clarify `--strict-go` behavior for non-T-SQL dialects.

**Acceptance Criteria**
1. Invalid dialect fails fast and lists supported values.
2. Help output documents Hive support and batch semantics by dialect.
3. CLI behavior is covered by tests.

---

### DOC-001 Rewrite README + Specs for Multi-dialect
**Goal**: Align documentation with implementation.

**Scope**
1. Update `README.md` from T-SQL-centric positioning to dialect-aware positioning.
2. Add support matrix and caveats per dialect.
3. Add Hive command and workflow examples.
4. Update spec docs to remove obsolete T-SQL-only assumptions.

**Acceptance Criteria**
1. Documentation no longer implies T-SQL-only scope.
2. Hive workflow is documented end-to-end.
3. Unsupported constructs and limitations are explicit.

---

### QA-001 Final Validation and Release Checklist
**Goal**: Ship safely with no critical regressions.

**Scope**
1. Run full test suite for T-SQL and Hive paths.
2. Add smoke tests for larger scripts and mixed quote styles.
3. Confirm deterministic outputs with fixed seeds per dialect.
4. Validate workspace integrity and schema evolution behavior.

**Acceptance Criteria**
1. CI is green for all test targets.
2. No high-severity regressions in T-SQL workflows.
3. Release notes include workspace schema compatibility/migration notes.

---

## Hive-focused Test Scenarios to Prioritize
1. Backtick identifiers: ``SELECT `user_id` FROM `users`;``
2. No `GO` splitting in Hive mode, even if token appears in text.
3. `INSERT OVERWRITE` and partition clauses.
4. LATERAL VIEW usage and complex type references.
5. Roundtrip deobfuscation preserving Hive quoting and parseability.

## Known Risk Areas
1. Workspace schema migration and backward compatibility policy.
2. Reverse-mapping ambiguity under dialect-specific AST differences.
3. SQL emission differences between dialects in `sqlglot`.
4. Hidden T-SQL assumptions in older tests/docs causing false failures.

## Notes
1. Milestone approach is strongly recommended:
   - Milestone 1: architecture refactor with T-SQL parity.
   - Milestone 2: Hive MVP coverage.
   - Milestone 3: edge-case hardening and documentation completion.
2. Avoid parallel behavior changes and schema changes in the same PR unless tightly scoped and fully tested.
