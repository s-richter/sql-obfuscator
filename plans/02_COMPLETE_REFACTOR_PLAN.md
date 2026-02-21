# Complete Refactor Plan (Functionality Parity, Improved Architecture, No Legacy Mode)

## 1. Objective

Refactor `sql-obfuscator` to a cleaner, testable, dialect-ready architecture while preserving existing functional behavior (obfuscate/deobfuscate/roundtrip/workspace integrity/reporting), with one explicit product change:

1. Remove legacy CLI mode (`python obfuscator.py <sql_file>` fallback).

Primary quality goals:
1. Architectural separation of concerns.
2. Strong schema/version discipline.
3. Dialect strategy abstraction as first-class design.
4. Test-first implementation with prominent regression safety.

---

## 2. Target Architecture

## 2.1 Layered Design

1. `domain/`
   - Identifier normalization and mapping models.
   - Deobfuscation resolution logic.
   - Dialect profile contracts and implementations.

2. `application/`
   - Use-case services:
     - `ObfuscateService`
     - `DeobfuscateService`
     - `RoundtripService`
     - `WorkspaceInfoService`
   - Orchestrates domain + infrastructure.

3. `infrastructure/`
   - Workspace read/write, integrity hashing, schema validation.
   - SQL parser/renderer adapter (sqlglot wrapper).
   - File/template I/O adapters.

4. `interfaces/cli/`
   - Pure argument parsing and command routing.
   - No business logic.

## 2.2 Dialect Strategy

Implement `DialectProfile` and factory:
1. `TsqlProfile` (parity baseline).
2. `HiveProfile` (MVP support).

Dialect profile responsibilities:
1. Batch split/join semantics.
2. Identifier normalization and temp-prefix behavior.
3. Identifier safety/keyword checks.
4. Quote extraction/restoration behavior.
5. Optional dialect-specific AST quirks.

## 2.3 Data Contracts

Replace raw dict-first behavior with typed models (dataclasses or pydantic/attrs):
1. `MappingPayload`
2. `ContextPayload`
3. `IntegrityPayload`
4. `DeobfuscationReport`
5. `RoundtripReport`

Add explicit schema migration path:
1. Reader supports old + current schema versions.
2. Writer emits current version only.
3. Actionable compatibility errors.

---

## 3. Non-Negotiable Product Decisions

1. Remove legacy CLI mode.
2. CLI requires subcommands only: `obfuscate`, `deobfuscate`, `roundtrip`, `workspace-info`.
3. Preserve existing command semantics and output artifacts unless explicitly changed by this plan.
4. Preserve deterministic behavior with `--seed`.
5. Preserve integrity check guarantees.

---

## 4. Refactor Milestones and Tasks

## Milestone A: Baseline Lock and Test Harness Hardening

### A1. Baseline behavior capture
1. Freeze current behavior with characterization tests for:
   - temp/global temp roundtrip
   - type lexeme restoration
   - workspace artifact layout
   - normalized roundtrip reports
2. Capture current CLI output text contracts where externally relied upon.

### A2. Test infrastructure improvements
1. Introduce test fixtures for:
   - command outputs
   - sample SQL corpus
   - workspace snapshots
2. Ensure tests avoid environment-specific tempdir failures where possible.

Acceptance:
1. Existing suite green.
2. Added characterization tests green.

---

## Milestone B: Introduce Core Architecture Skeleton (No Behavior Change)

### B1. Create package layout
1. Add `domain`, `application`, `infrastructure`, `interfaces/cli` modules.
2. Add adapter interfaces for parser/renderer and workspace store.

### B2. Move logic without semantic changes
1. Extract workspace operations from `workspace.py` into infrastructure services.
2. Extract orchestration from `cli.py` into application services.
3. Keep old modules as thin forwarding wrappers during transition.

Acceptance:
1. All tests green.
2. CLI behavior unchanged except internal implementation.

---

## Milestone C: Dialect Profile Abstraction

### C1. Define dialect contract
1. Add `DialectProfile` base contract.
2. Add profile factory and supported-dialect registry.

### C2. Implement `TsqlProfile` parity
1. Move current T-SQL-specific behavior from:
   - `go_batches.py`
   - `registry.normalize_identifier`
   - `names.py` safety logic
   - quote restoration logic in deobfuscation
2. Ensure no user-visible behavior changes for `--dialect tsql`.

### C3. Wire all flows through profile
1. Obfuscation pipeline uses profile for split/join/normalization/safety.
2. Deobfuscation uses profile for quote semantics and identifier restoration.

Acceptance:
1. T-SQL regression suite green.
2. No direct hard-coded T-SQL logic in orchestration layer.

---

## Milestone D: CLI Refactor and Legacy Mode Removal

### D1. Remove legacy dispatch
1. Delete `_is_subcommand_mode` branching behavior.
2. Make subcommand parser mandatory.
3. Update entry points and help text.

### D2. Modern CLI contract validation
1. Validate dialect against profile registry.
2. Improve error messaging for invalid inputs and schema issues.

Acceptance:
1. Legacy invocation fails with clear guidance.
2. Subcommand workflows all green.

---

## Milestone E: Typed Payload Models and Schema Versioning

### E1. Introduce typed payload models
1. Replace ad hoc dict access in core flow.
2. Centralize serialization/deserialization.

### E2. Implement migration layer
1. Add versioned loaders for mapping/context/integrity.
2. Add conversion logic for old versions where feasible.
3. Add explicit migration errors where not feasible.

### E3. Expand schema tests
1. Add positive/negative tests per schema version.
2. Add roundtrip serialization compatibility tests.

Acceptance:
1. Current-format payloads remain readable.
2. CI protects schema compatibility guarantees.

---

## Milestone F: Hive MVP on New Architecture

### F1. Implement `HiveProfile`
1. Hive-safe identifier rules.
2. Hive keyword set integration.
3. Hive quote semantics (backticks).
4. Hive batch behavior (no T-SQL GO semantics).

### F2. Add Hive fixture corpus
1. `sample_sql/hive/` scripts:
   - joins/cte
   - insert overwrite
   - partition examples
   - alias-heavy cases

### F3. Hive E2E tests
1. Obfuscate/deobfuscate roundtrip.
2. Dry-run unknown/ambiguous behavior.
3. Parseability checks with `dialect="hive"`.

Acceptance:
1. Hive MVP path green in CI.
2. T-SQL path remains green.

---

## Milestone G: Cleanup, Performance, and Documentation

### G1. Remove transitional wrappers
1. Delete deprecated forwarding code.
2. Consolidate module ownership and imports.

### G2. Performance pass
1. Eliminate duplicate parse operations where possible.
2. Profile large script behavior.
3. Add simple performance regression checks.

### G3. Documentation refresh
1. Rewrite README for subcommand-only CLI.
2. Add architecture section and support matrix.
3. Add migration notes and breaking-change notes.

Acceptance:
1. No dead code from transition.
2. Docs match behavior.

---

## 5. Test Strategy (Prominent Role)

## 5.1 Test Categories

1. Unit tests
   - profile behavior (batch/safety/normalization/quoting)
   - registry and resolver logic
   - schema model validation

2. Integration tests
   - full obfuscate/deobfuscate cycles
   - roundtrip report correctness
   - workspace integrity checks

3. Contract tests
   - CLI stdout/stderr and exit codes
   - artifact paths and report fields

4. Compatibility tests
   - legacy workspace payload reads
   - schema migration behavior

5. Dialect matrix tests
   - identical test intents for `tsql` and `hive` where applicable.

## 5.2 Test Gates per PR

Required:
1. Unit tests for changed modules.
2. Relevant integration tests.
3. T-SQL regression subset.
4. Lint/type checks if introduced.

For milestone-completion PRs:
1. Full test suite.
2. Dialect matrix subset.
3. Schema compatibility tests.

## 5.3 Golden/Snapshot Testing

1. Add curated fixtures for mapping/context/report payload snapshots.
2. Use normalized comparison for SQL format-sensitive outputs.
3. Keep explicit semantic assertions for critical fields.

## 5.4 Failure-Mode Testing

1. Parse failures with batch context.
2. Unknown/ambiguous identifier reporting.
3. Integrity checksum mismatch behavior.
4. Unsupported dialect error behavior.
5. Invalid schema version behavior.

---

## 6. Migration and Rollout Plan

1. Use feature branches per milestone.
2. Keep milestones mergeable and independently testable.
3. Prefer small PRs with clear boundaries:
   - architecture scaffolding
   - logic relocation
   - behavior changes
   - schema/version updates
4. Publish migration notes before removing legacy mode.

---

## 7. Risks and Mitigations

1. Risk: Hidden behavior regressions during module moves.
   - Mitigation: characterization tests first (Milestone A).

2. Risk: Schema breakages for existing workspaces.
   - Mitigation: migration layer + compatibility tests.

3. Risk: Dialect abstraction leaks.
   - Mitigation: profile contract coverage and forbidden direct imports checks.

4. Risk: CLI breaking changes cause user confusion.
   - Mitigation: explicit error guidance and documentation updates.

---

## 8. Definition of Done

Project is done when:
1. New layered architecture is in place.
2. Legacy mode is removed.
3. T-SQL behavior is preserved under subcommand usage.
4. Hive MVP is supported via profile architecture.
5. Schema/version compatibility behavior is explicit and tested.
6. Test suite has strong unit/integration/contract/compatibility coverage.
7. Documentation fully reflects new architecture and CLI behavior.

---

## 9. Suggested Execution Order (High-Level)

1. A -> B -> C -> D -> E -> F -> G
2. Do not parallelize schema-version change and Hive behavior change in one PR.
3. Keep T-SQL parity green at every milestone before proceeding.

