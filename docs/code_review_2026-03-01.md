# Code Review 2026-03-01

## Scope

Review of the current `sql-obfuscator` application, including core runtime code, CLI behavior, workspace persistence, test coverage, and repository documentation.

## Status Update

This review has now been actioned. The findings documented below were implemented after the original review and are fixed in the current workspace state.

Implemented follow-up:

- Fixed `UPDATE` alias-target obfuscation in `src/sql_obfuscator/transformer.py`
- Made workspace persistence remove stale optional artifacts such as `redaction.json` and `translated.sql`
- Changed translate workspace artifact persistence so failed runs and `--stdout-only` runs do not leave `translated.sql`
- Aligned CLI help `prog` with the installed console script name `sql-obfuscator`
- Updated packaging metadata to declare runtime text assets and to describe both supported dialects
- Updated README/tutorial wording to match actual CLI behavior
- Strengthened regression coverage for the above cases

Verification performed:

- Static review of the main modules under `src/sql_obfuscator/`
- Review of the test suite under `tests/`
- Review of `README.md`, `docs/COMMAND_TUTORIAL.md`, and packaging metadata
- Selective test execution in the local environment

Execution note:

- Focused test runs succeeded for `tests/test_names.py`, `tests/test_identifier_safety.py`, `tests/test_suite_coverage.py`, and `tests/test_pipeline.py`.
- Broad `pytest` runs in this environment were limited by Windows temp-directory permission/cleanup issues, so some conclusions below rely on direct reproduction scripts plus static inspection.

## Findings

### 1. High: `UPDATE` alias targets are obfuscated incorrectly because the alias-specific branch is unreachable

Status: Fixed

Files:

- `src/sql_obfuscator/transformer.py:116-149`
- `tests/test_transformer.py:36-44`

The `UPDATE` alias-target special case in `_rename_table()` is indented under the `if not isinstance(identifier, exp.Identifier): return table` branch, so it never executes. As written, `UPDATE u SET ... FROM Users u` is obfuscated as if `u` were a table name, not an alias target.

Observed reproduction:

- Input: `UPDATE u SET u.UserId = 1 FROM Users u`
- Output: `UPDATE eastern_ape SET cloudy_gerbil.spruce_eagle = 1 FROM humble_peacock AS cloudy_gerbil`

That changes the statement from "update the aliased rowset from `FROM Users u`" into "update a different target name entirely", which is a semantic bug and can produce invalid SQL.

The existing regression test is too weak to catch this. `tests/test_transformer.py:36-44` only checks that the output no longer starts with `UPDATE u` and that `AS u` disappeared, but it does not assert that the `UPDATE` target and `FROM` alias stay consistent.

Resolution:

- The unreachable branch in `src/sql_obfuscator/transformer.py` was fixed so update alias targets are now obfuscated via the alias path.
- `tests/test_transformer.py` was strengthened to assert that the `UPDATE` target alias and the `FROM ... AS ...` alias remain the same obfuscated identifier.

### 2. Medium: Reusing a workspace can leave stale `redaction.json` behind and cause false deobfuscation failures

Status: Fixed

Files:

- `src/sql_obfuscator/workspace.py:134-142`
- `src/sql_obfuscator/cli.py:504-513`

`save_workspace_artifacts()` writes `redaction.json` only when `redaction_payload` is present, but it never removes old redaction artifacts when a workspace is reused for a later non-redacted run. `_deobfuscate_pipeline()` then loads `redaction.json` purely based on file existence.

This means a workspace that was once created with reversible redaction can poison later runs that do not use redaction. In direct reproduction, the second run deobfuscated SQL correctly, but reversible-redaction restoration still executed and reported `missing_placeholder_count = 1` from the stale metadata.

Impact:

- False `deobfuscate --dry-run` failures
- False `validate-before-write` failures
- Confusing workspace state that integrity checks do not catch, because the stale file is no longer tracked in the new `integrity.json`

Resolution:

- `src/sql_obfuscator/workspace.py` now removes stale `redaction.json` and `redaction.schema.json` when a workspace is reused for a run that does not produce redaction metadata.
- Regression coverage was added to verify stale redaction artifacts are removed on reuse.

### 3. Medium: Translation artifact persistence ignores both failure state and `--stdout-only` semantics

Status: Fixed

Files:

- `src/sql_obfuscator/cli.py:835-848`
- `src/sql_obfuscator/workspace.py:253-268`
- `README.md:80-85`
- `README.md:328-335`
- `docs/COMMAND_TUTORIAL.md:556-565`
- `docs/COMMAND_TUTORIAL.md:664-664`

`_run_translate_command()` saves translation artifacts before checking whether translation/validation failed, and it passes `translated_sql` whenever `args.out is None and not args.report_only`. That has two problematic effects:

- A failed translation run can still write `<workspace>/translated.sql`
- `translate --stdout-only --workspace ...` still writes `<workspace>/translated.sql`

Direct reproduction confirmed both behaviors:

- A forced validation failure returned exit code `1` but still wrote `translated.sql`
- `--stdout-only` still wrote `translated.sql` when `--workspace` was supplied

This is risky for automation because a non-zero command can still leave behind a plausible-looking translated output artifact, and `--stdout-only` no longer means "stdout only" once a workspace is involved.

This also conflicts with the docs, which currently say:

- "Translate from file and print translated SQL only" in `README.md:80-85`
- "`--stdout-only`: print translated SQL to stdout without writing translated SQL output files" in `README.md:328-335`
- Similar wording in `docs/COMMAND_TUTORIAL.md`

Resolution:

- `src/sql_obfuscator/cli.py` now treats translation success as a prerequisite before persisting `translated.sql`.
- `src/sql_obfuscator/workspace.py` now removes stale `translated.sql` when no translated SQL should be persisted.
- `translate --stdout-only --workspace ...` no longer writes `translated.sql`.
- Failed translation/validation runs no longer leave behind `translated.sql`.
- `tests/test_cli.py` and `tests/test_workspace.py` were expanded to cover these behaviors.
- README/tutorial wording was updated to reflect that stdout mode prints the summary line plus translated SQL and writes no translated SQL artifact, including workspace `translated.sql`.

### 4. Low: The installed console script exposes help text as `obfuscator.py`, not `sql-obfuscator`

Status: Fixed

Files:

- `src/sql_obfuscator/cli.py:213-217`
- `pyproject.toml:20-21`
- `README.md:26-30`

The package installs `sql-obfuscator` as the console script, but `build_command_parser()` hardcodes `prog="obfuscator.py"`. That means installed help text and usage banners identify the tool by a different name than the packaged entry point and the README.

This is not a runtime correctness bug, but it is a documentation/UX inconsistency that will confuse users copying help output into docs, tickets, or CI logs.

Resolution:

- `src/sql_obfuscator/cli.py` now uses `prog="sql-obfuscator"`.
- `pyproject.toml` was updated to describe both supported dialects and declare runtime `.txt` package assets.
- Packaging and docs-consistency tests were strengthened accordingly.

## Test Coverage Assessment

### Strengths

- Coverage is broad across the main subsystems: CLI, transformer, deobfuscation, translation, workspace persistence, dialect handling, docs consistency, and packaging metadata.
- There are many behavior-oriented tests, not just unit tests for helpers.
- The suite already checks deterministic seeding, reversible redaction, roundtrip flows, and multiple dialect paths.

### Gaps

- `UPDATE` alias-target handling is not asserted strongly enough. `tests/test_transformer.py:36-44` allows the current semantic regression through.
- There is no test for workspace reuse across runs with different redaction modes, which is why stale optional artifacts were able to survive unnoticed.
- `tests/test_cli.py:1057-1078` checks that `translate --stdout-only` skips the sibling file, but it does not check that no workspace SQL artifact is written and does not check that stdout contains SQL only.
- `tests/test_cli.py:979-1008` checks that translation validation failure returns non-zero, but it does not assert that no success-looking SQL artifact was written to the workspace.
- `tests/test_packaging.py:7-12` only checks the console entry point. It does not verify that an actual built wheel/sdist contains the runtime text assets (`identifier_adjectives.txt`, `identifier_replacements.txt`, `*_reserved_keywords.txt`) that are loaded directly from package files.
- `tests/test_docs_consistency.py:17-42` only checks for the presence of flag strings in help/docs. It does not verify whether the documented semantics are actually true.

Status update on coverage gaps:

- The first four gaps above are now fixed by added regression coverage.
- The packaging test now verifies package-data declaration in `pyproject.toml`, which is an improvement, but a true build-and-inspect packaging test is still not present.
- The docs consistency checks now verify the updated `translate --stdout-only` semantics in the docs, not just flag presence.

## Documentation Assessment

### Accurate areas

- The README is comprehensive and covers most commands, workspace artifacts, and safety flags.
- The command tutorial is detailed and useful for scenario-based usage.

### Mismatches / Risks

- The translate `--stdout-only` documentation is currently stronger than the implementation. The docs promise SQL-only/no output files, but the CLI always prints a summary line first and can still persist `translated.sql` when `--workspace` is used.
- The installed command name in packaging/docs is `sql-obfuscator`, but help output uses `obfuscator.py`.
- `pyproject.toml:8` still describes the package as "for T-SQL scripts" even though the README and implementation clearly support both `tsql` and `hive`.

Status update on documentation mismatches:

- These documented mismatches are fixed in the current workspace state.

## Recommended Next Fixes

The original recommended fixes from this review have been implemented.

Remaining worthwhile follow-up:

1. Add a true package-build test that inspects a built wheel/sdist to confirm the runtime text assets are actually included, rather than only verifying `pyproject.toml` declarations.
2. Resolve the local Windows pytest temp-directory permission issue so the full test suite can run cleanly in this environment without relying on direct runtime probes for some `tmp_path`-based checks.
