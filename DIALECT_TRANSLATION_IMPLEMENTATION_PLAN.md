# SQL Dialect Translation Feature Plan

## Purpose
Add a first-class `translate` capability that converts SQL scripts between supported dialects (initially `tsql` and `hive`) while preserving existing obfuscation/deobfuscation workflows and quality guarantees.

## Scope
- In scope:
  - New CLI subcommand for standalone translation.
  - Reusable translation service module.
  - Batch-aware translation using dialect profiles.
  - Translation reporting (success/failure/warnings).
  - Validation mode (target parseability check).
  - Unit + integration + regression tests.
- Out of scope (first delivery):
  - Guaranteed semantic equivalence.
  - Automatic data-type/function semantic rewrites beyond what sqlglot provides.
  - Full cross-dialect canonicalization engine.

## CLI Contract

### Command
```bash
python obfuscator.py translate --input <input.sql> --source-dialect <dialect> --target-dialect <dialect> [options]
```

### Required Args
- `--input <path>`: input SQL file.
- `--source-dialect <name>`: parser dialect, must be in `supported_dialects()`.
- `--target-dialect <name>`: output dialect, must be in `supported_dialects()`.

### Optional Args
- `--out <path>`: output SQL path.
  - Default: `<input_stem>_<target_dialect>.sql`.
- `--pretty` / `--no-pretty`:
  - Default: `--pretty`.
- `--validate`:
  - Parse translated output using target dialect and fail on parse errors.
- `--workspace <path>`:
  - Optional workspace/report destination for translation artifacts.
  - If omitted, command still works and only writes translated SQL + stdout summary.
- `--report-only`:
  - Do not write translated SQL, only produce validation/report output.

### Exit Codes
- `0`: Translation completed and (if enabled) validation passed.
- `1`: Input/read/parse/translation/validation/report write failure.

### Output Behavior
- Always prints concise summary:
  - source dialect, target dialect, statement count, failed statement count, warning count.
- Writes translated SQL unless `--report-only`.
- If workspace/reporting enabled, writes `reports/translation_report.json`.

## Architecture

### New Module
- `src/sql_obfuscator/translation.py`

### Core API
- `translate_sql(script: str, *, source_dialect: str, target_dialect: str, pretty: bool = True, validate: bool = False) -> str`
- `translate_sql_with_report(...) -> TranslationResult`

### `TranslationResult` Dataclass
- `output_sql: str`
- `source_dialect: str`
- `target_dialect: str`
- `batch_count: int`
- `statement_count: int`
- `translated_statement_count: int`
- `failed_statement_count: int`
- `warnings: list[str]`
- `failures: list[dict[str, Any]]`
- `validated: bool`

### Pipeline Logic
1. Resolve `source_profile` and `target_profile` via `get_dialect_profile`.
2. Split input with `source_profile.split_batches`.
3. Parse each non-empty batch using `sqlglot.parse(batch, dialect=source_dialect)`.
4. Emit each statement with `stmt.sql(dialect=target_dialect, pretty=pretty)`.
5. Rejoin translated batches via `target_profile.join_batches`.
6. If `validate`:
   - Parse translated batches with target dialect.
   - Collect parse failures by batch index + snippet.
7. Return `TranslationResult`.

### Error Model
- Reuse existing domain errors:
  - `InputFileError`
  - `ParseScriptError`
  - `WorkspaceError`
- Add `TranslationError` only if needed for clear separation.

### Workspace Integration
- Optional, non-breaking:
  - `reports/translation_report.json`
  - `translated.sql` (if workspace path supplied and no explicit `--out`)
- Do not alter existing obfuscation workspace contract for current commands.

## Interactions with Obfuscation/Deobfuscation

### Supported Combined Flows
1. `obfuscate(source) -> translate(obfuscated, source->target) -> LLM -> translate(back) -> deobfuscate(source)`
2. `translate(source->target) -> obfuscate(target) -> LLM -> deobfuscate(target)`

### Rule
Keep translation as an independent stage. Do not couple translation code into identifier registry/transformer logic.

### Risk Note
Deobfuscation relies on obfuscated identifier continuity. Translation can alter quoting/casing/token forms. Reports must flag potential identifier shape changes.

## Milestones and Tasks

## Milestone 1: Foundation (`translation.py`)
### Tasks
1. Create `TranslationResult` and public APIs.
2. Implement batch-aware translation with profile split/join.
3. Implement failure aggregation per batch/statement.
4. Add validation pass (`--validate` equivalent behavior).
5. Add unit tests for happy path and parse failures.

### Acceptance Criteria
- `translate_sql_with_report` handles multi-batch scripts and returns structured report.
- Works for `tsql -> hive` and `hive -> tsql` basic scripts.

## Milestone 2: CLI Integration
### Tasks
1. Add `translate` subcommand in `src/sql_obfuscator/cli.py`.
2. Add argument parsing, output path defaults, and summary print.
3. Wire report-only and validate options.
4. Wire optional workspace/report writing.
5. Add CLI tests for:
   - success path
   - parse error path
   - validate failure path
   - output file path behavior

### Acceptance Criteria
- `python obfuscator.py translate ...` works end-to-end with deterministic file behavior.
- Exit codes match contract.

## Milestone 3: Reporting and Workspace Artifacts
### Tasks
1. Add helper in `workspace.py` to save translation report safely.
2. Define translation report JSON schema (optional but recommended).
3. Include integrity checks only if translation artifacts are promoted to protected files.
4. Add workspace-info output line for translation artifacts presence.

### Acceptance Criteria
- Report written reliably and validated.
- Existing workspace integrity behavior remains backward compatible.

## Milestone 4: Cross-Dialect Regression Suite
### Tasks
1. Add fixture scripts for dialect-sensitive features:
   - temp tables
   - quoted identifiers
   - CTEs
   - joins/aggregates
   - function/date expressions
2. Add golden-ish assertions:
   - parseable in target dialect
   - expected structural markers present
3. Add edge-case tests for unsupported constructs with warnings/failures.

### Acceptance Criteria
- Test suite clearly identifies where sqlglot translation is lossy or unsupported.
- No regressions in current obfuscation/deobfuscation test suites.

## Milestone 5: Documentation and Operational Guidance
### Tasks
1. Update `README.md`:
   - command usage
   - examples per dialect pair
   - limitations and risk notes
2. Add troubleshooting section for translation failures.
3. Add recommended combined workflow diagrams/snippets.

### Acceptance Criteria
- Users can run translation confidently and understand limitations.

## Test Strategy

## Unit Tests
- `tests/test_translation.py`
  - single-statement translation success.
  - multi-batch source handling.
  - empty batch passthrough behavior.
  - validation toggle behavior.
  - failure record structure.

## CLI Tests
- `tests/test_cli.py` additions:
  - `translate` writes output file and returns `0`.
  - `translate --report-only` does not write SQL output.
  - invalid dialect returns non-zero with clear error.
  - `--validate` failure returns non-zero.

## Integration Tests
- `tests/test_llm_workflow_integration.py` additions:
  - obfuscate -> translate -> translate back -> deobfuscate dry-run clean on controlled script.

## Non-Functional Tests
- Performance smoke on larger SQL file (statement count benchmark).
- Determinism check for same input/options.

## Implementation Notes
- Prefer `source_profile.sqlglot_dialect` and `target_profile.sqlglot_dialect` if profile naming diverges from CLI names.
- Keep comments and formatting expectations explicit: translation is structural, not byte-preserving.
- Ensure report includes concrete indexes (`batch_index`, `statement_index`) for actionable debugging.

## Risks and Mitigations
- Risk: Unsupported source syntax.
  - Mitigation: Per-batch parse errors and fail-fast with context snippet.
- Risk: Target dialect parse succeeds but semantics drift.
  - Mitigation: document limitation; add optional structural comparison hooks later.
- Risk: Identifier quoting changes impact deobfuscation workflows.
  - Mitigation: warn when identifier tokenization/quoting pattern changes significantly.

## Suggested Delivery Order
1. Milestone 1
2. Milestone 2
3. Milestone 4 (early feedback loop)
4. Milestone 3
5. Milestone 5

This order gets user-visible value early while preserving engineering confidence via tests.
