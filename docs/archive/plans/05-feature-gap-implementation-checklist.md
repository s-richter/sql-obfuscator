# 05 Feature Gap Implementation Checklist

## Goal

Close the high-impact product gaps identified in current CLI/documentation behavior, prioritized by user impact and implementation risk.

## Priority Model

- `P0`: correctness/usability bug causing surprising behavior
- `P1`: expected CLI behavior for production usage
- `P2`: strategic expansion or broader ecosystem support

## P0 - Correctness And UX Consistency

### 1) `validate-before-write --dry-run` behavior mismatch

- [x] Decide behavior contract:
  - [ ] Option A: support true dry-run in `validate-before-write`
  - [x] Option B: remove `--dry-run` from this command
- [x] Implement chosen behavior in CLI command handler.
- [x] Add/adjust tests:
  - [ ] verify no file writes in dry-run (if Option A)
  - [x] verify argparse rejects/removes dry-run for command (if Option B)
- [x] Update command help text and docs to match.

Acceptance criteria:

- [x] CLI behavior, `-h` help output, and docs all agree.
- [x] Regression tests cover this path.

### 2) `roundtrip --diff-report` help text stale

- [x] Update help string for `--diff-report` to reflect implemented behavior.
- [x] Add a lightweight CLI help test assertion for expected wording.
- [x] Confirm README/tutorial wording remains aligned.

Acceptance criteria:

- [x] `python obfuscator.py roundtrip -h` describes real behavior.

## P1 - Expected CLI/Product Surface

### 3) `--strict-go` is currently no-op

- [x] Define strict semantics explicitly:
  - [x] what constitutes unsafe/invalid `GO` usage
  - [x] expected error messages and exit behavior
- [x] Implement strict validation in batch split/join pipeline.
- [x] Add tests for:
  - [x] valid strict cases
  - [x] invalid strict cases
  - [x] non-strict backward-compatible behavior
- [x] Update docs with concrete examples.

Acceptance criteria:

- [x] `--strict-go` materially changes behavior and is test-covered.
- [x] Non-strict mode remains backward compatible.

### 4) Installable console entry point

- [x] Add `[project.scripts]` entry in `pyproject.toml` (for example `sql-obfuscator = sql_obfuscator.cli:main`).
- [ ] Verify editable install exposes console command.
  - Note: blocked in current environment by temp-dir permission errors during `pip install -e .`.
- [x] Add a smoke test/documented command invocation for installed mode.
- [x] Update README to show both wrapper and console command usage.

Acceptance criteria:

- [ ] After install, command runs without `python obfuscator.py`.

### 5) Automation-friendly input modes

- [x] Add stdin support (`-` as input) for `obfuscate`, `roundtrip`, and `translate`.
- [x] Add optional stdout-only mode where appropriate (no sibling file write).
- [x] Evaluate `--output-dir` or batch glob mode for multi-file workflows.
  - Implemented `--output-dir` for file-input workflows.
- [x] Add tests for pipeline usage:
  - [x] `cat input.sql | ...`
  - [x] stdin + workspace creation behavior
  - [x] deterministic outputs with seeds in stdin path
- [x] Document CI-friendly usage patterns.

Acceptance criteria:

- [x] Core commands can be used in shell pipelines without temporary files.

## P2 - Strategic Expansion

### 6) Dialect coverage expansion roadmap

- [ ] Define next dialect set (recommended order):
  - [ ] `postgres`
  - [ ] `mysql`
  - [ ] `snowflake`
  - [ ] `bigquery`
- [ ] For each dialect:
  - [ ] add profile in `dialects_*`
  - [ ] add factory registration
  - [ ] add obfuscation/deobfuscation tests
  - [ ] add translation tests both directions for supported pairs
- [ ] Add compatibility matrix to README.

Acceptance criteria:

- [ ] New dialects appear in CLI choices and are covered by tests/docs.

## Cross-Cutting Work

### Testing And Quality Gates

- [x] Add/extend CLI contract tests for every command's `-h` output.
- [x] Add doc consistency check (optional script) for flags/defaults.
- [x] Ensure CI runs fast subset + full suite for release branches.

### Documentation Synchronization

- [x] Update `README.md` command reference after each feature merge.
- [x] Update `docs/guides/command-tutorial.md` with one realistic example per new capability.
- [x] Track known limitations in a single `Current Limits` section.

## Suggested Delivery Sequence

1. `P0.1` dry-run mismatch
2. `P0.2` diff-report help text
3. `P1.4` console entry point
4. `P1.3` strict-go implementation
5. `P1.5` stdin/pipeline support
6. `P2.6` dialect expansion

## Definition Of Done (Plan Level)

- [ ] No known mismatch between runtime behavior, help text, tests, and docs.
- [ ] Core workflows support both local developer usage and CI automation.
- [ ] Release notes include any behavior changes and migration notes.
