# Unified Multi-Dialect Expansion Plan (T-SQL + Hive/Cloudera)

## Purpose

This document unifies architectural analysis and executable planning for evolving `sql-obfuscator` from T-SQL-centric behavior to a robust multi-dialect system with first-class Hive SQL (Cloudera) support.

It combines:
1. Strategy options and tradeoffs.
2. Recommended target architecture.
3. Concrete implementation milestones/tasks.
4. Acceptance criteria and risk controls.

---

## Current Constraints

1. Core behavior still assumes T-SQL in several modules despite `--dialect` existing.
2. `GO` batch splitting is effectively T-SQL-specific and can be incorrect for Hive.
3. Identifier safety checks are tied to T-SQL reserved keywords.
4. Quote assumptions (`[name]`) are embedded in normalization/deobfuscation paths.
5. Tests/docs are largely T-SQL focused and do not fully protect dialect-specific behavior.

---

## Strategy Options

## Option 1: Incremental Patchwork (quickest, least durable)

### Summary
Keep current architecture and add dialect conditionals in-place (batch logic, keywords, quoting).

### Pros
1. Fastest initial delivery.
2. Minimal initial refactor.

### Cons
1. Conditionals spread across codebase.
2. Harder to reason about correctness over time.
3. Higher regression risk as dialect count grows.
4. Poor long-term maintainability.

### Use case
Only viable as short-lived stopgap.

---

## Option 2: Dialect Strategy Layer (recommended)

### Summary
Introduce a `DialectProfile` abstraction and move all dialect-sensitive rules behind profile interfaces.

### Pros
1. Strong maintainability and extensibility.
2. Concentrated dialect logic.
3. Cleaner tests and lower regression risk.
4. Preserves current AST pipeline and existing strengths.

### Cons
1. Medium refactor effort.
2. Requires schema/metadata evolution for quote handling and compatibility.

### Use case
Best balance for current and future dialect support.

---

## Option 3: External Plugin Ecosystem (max flexibility, highest complexity)

### Summary
Design plugin-based dialect packs (rules, keywords, fixtures, validations).

### Pros
1. Maximum extensibility and modularity.
2. Good for large contributor ecosystems.

### Cons
1. Highest complexity and operational overhead.
2. Premature for current project scope.

### Use case
Future consideration if dialect count or contributor count grows significantly.

---

## Recommendation

Adopt **Option 2: Dialect Strategy Layer**.

Reasoning:
1. Delivers Hive support without accumulating brittle conditional logic.
2. Keeps T-SQL parity possible while refactoring.
3. Scales to additional dialects with bounded complexity.
4. Aligns with existing architecture and test model.

---

## Target Architecture (Option 2)

## 1. Dialect Profile Abstraction

Add a dialect package:
1. `src/sql_obfuscator/dialects/base.py`
2. `src/sql_obfuscator/dialects/factory.py`
3. `src/sql_obfuscator/dialects/tsql.py`
4. `src/sql_obfuscator/dialects/hive.py`

Proposed interface (minimum):
1. `name`
2. `split_batches(script: str) -> list[str]`
3. `join_batches(batches: list[str]) -> str`
4. `normalize_identifier(raw: str) -> IdentifierKeyLike`
5. `is_safe_identifier(name: str) -> bool`
6. `extract_quote_metadata(raw_identifier: str) -> QuoteMetadata`
7. `apply_quote_metadata(identifier_node, quote_metadata) -> None`

Optional profile hooks:
1. `render_temp_table_lexeme(...)`
2. `parse_type_lexeme(...)` variations by dialect.

## 2. Pipeline/Deobfuscation Wiring

Refactor core flow to resolve a profile once, then use it everywhere dialect-sensitive:
1. batch split/join
2. identifier normalization
3. safety checks
4. quoting restoration

Keep shared AST rename/deobfuscation logic as dialect-neutral as possible.

## 3. Names and Reserved Keywords

Move from T-SQL-global safety logic to profile-driven safety:
1. `AnimalNameProvider` takes profile safety predicate.
2. per-dialect keyword sets loaded by profile.
3. identifier regex/lexical constraints are dialect-aware.

### Keyword File Scalability Position

Text keyword files are acceptable baseline assets, but not sufficient alone at scale.

Required controls:
1. file-per-dialect (and dialect-version where needed).
2. loaded through profile, never global hard-coded constants.
3. CI validation for non-empty, deduped, normalized entries.
4. quote/normalization rules treated as separate profile concerns.

## 4. Quote and Mapping Metadata

Evolve mapping metadata from T-SQL-specific bracket semantics to dialect-neutral quote metadata.

Recommended direction:
1. deprecate narrow fields like `original_was_bracketed`.
2. store generic quote mode/style information.
3. keep backward compatibility for existing v1 workspaces.

## 5. Batch Semantics by Dialect

1. T-SQL profile: current `GO` behavior preserved.
2. Hive profile (MVP): no `GO` semantics; single-batch policy or Hive-correct batch handling.
3. future profiles can define their own separators/policies.

---

## Concrete Implementation Plan

## Milestone 1: Dialect Abstraction + T-SQL Parity

### Task 1.1: Create profile framework
1. Add dialect package (`base`, `factory`, profile registry).
2. Add clear error for unsupported dialect.

Acceptance:
1. `--dialect` validated against registry.
2. Existing default behavior unchanged (`tsql`).

### Task 1.2: Implement `TsqlProfile`
1. Encode current batch rules.
2. Encode current normalization/temp-prefix semantics.
3. Encode current quote behavior.
4. Encode T-SQL safety/keywords via profile.

Acceptance:
1. T-SQL behavior parity on current test suite.
2. No user-visible regression for current workflows.

### Task 1.3: Wire pipeline/deobfuscation through profile
1. Remove direct T-SQL helper coupling in core flow.
2. Use profile APIs for all dialect-sensitive decisions.

Acceptance:
1. Core modules no longer hard-code T-SQL assumptions.
2. Existing tests remain green.

---

## Milestone 2: Schema Evolution + Compatibility

### Task 2.1: Mapping/context schema update
1. Add dialect-neutral quote metadata model.
2. Update schema validation logic.
3. Decide and implement versioning policy.

Acceptance:
1. New artifacts validate.
2. Clear compatibility behavior for older workspaces.

### Task 2.2: Backward compatibility path
1. Support reading legacy workspace schema where feasible.
2. Emit explicit actionable errors when incompatible.

Acceptance:
1. Existing users can continue deobfuscation with legacy workspaces or receive clear migration guidance.

---

## Milestone 3: Hive Profile MVP

### Task 3.1: Implement `HiveProfile`
1. Add Hive keyword set.
2. Add Hive-safe identifier rules.
3. Add backtick quote handling.
4. Implement Hive batch policy (no T-SQL `GO` behavior).

Acceptance:
1. `--dialect hive` parse/obfuscate/deobfuscate works for baseline fixtures.
2. Output parses with SQLGlot Hive dialect.

### Task 3.2: CLI and UX updates
1. Update help text and validation.
2. Clarify dialect-specific batch behavior in docs.

Acceptance:
1. Invalid dialect fails fast with supported list.
2. Help/docs reflect real behavior.

---

## Milestone 4: Test Matrix and Fixtures

### Task 4.1: Lock T-SQL regression suite
1. Explicitly mark T-SQL assumptions where relevant.
2. Keep existing guarantees.

Acceptance:
1. Full T-SQL regression confidence maintained.

### Task 4.2: Add Hive fixture corpus
1. Create `sample_sql/hive/` fixtures.
2. Include backticks, insert overwrite, partition examples, alias-heavy scripts.

Acceptance:
1. Hive fixtures parse and roundtrip correctly.

### Task 4.3: Add Hive integration tests
1. Obfuscate/deobfuscate roundtrip.
2. dry-run unknown/ambiguous reporting.
3. verify no `GO` splitting behavior in Hive mode.

Acceptance:
1. CI path for Hive is green.

---

## Milestone 5: Documentation and Release Readiness

### Task 5.1: Documentation refresh
1. Rewrite README as dialect-aware.
2. Add support matrix and caveats.
3. Add end-to-end Hive examples.

### Task 5.2: QA and release checklist
1. Run full matrix (T-SQL + Hive).
2. Validate deterministic behavior per dialect with seeds.
3. Validate workspace integrity/schema behaviors.

Acceptance:
1. No high-severity regressions in T-SQL.
2. Hive MVP supported and documented.

---

## Risk Areas and Mitigations

## Risks

1. Schema migration complexity and backward compatibility.
2. Hidden T-SQL assumptions in legacy code/tests.
3. Dialect-specific AST differences causing reverse-mapping ambiguity.
4. SQLGlot emission differences across dialects.

## Mitigations

1. Sequence: abstraction first, behavior changes second.
2. Keep T-SQL parity gate throughout.
3. Add dialect fixtures early; grow integration tests before rollout.
4. Provide explicit compatibility policy and migration guidance.

---

## Deliverables Checklist

1. Dialect profile framework and factory.
2. `TsqlProfile` parity implementation.
3. `HiveProfile` MVP implementation.
4. Profile-driven names/safety.
5. Schema and compatibility updates.
6. Hive fixtures + tests.
7. Updated CLI UX/docs.
8. Release QA report.

