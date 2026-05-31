# Documentation Audit

Date: 2026-05-31

## Scope

Compared the user-facing documentation, especially `README.md` and
`docs/COMMAND_TUTORIAL.md`, against the CLI, workflow, privacy, redaction, and
workspace implementations. Also reviewed tracked specs, plans, and TODO notes
for documents that still present stale information as current.

## Findings

### 1. Resolved: `--llm-safe` failed for normal multi-batch T-SQL

`README.md:16` documents support for scripts separated by standalone `GO`
lines, and `README.md:159` documents `--llm-safe` for external sharing.

The obfuscation pipeline correctly splits and rejoins batches in
`src/sql_obfuscator/pipeline.py:196-219`. Before the fix, the privacy audit
reparsed the final joined SQL as one script. For T-SQL output containing
standalone `GO`, this could produce `privacy_audit_parse_error`, causing
`--llm-safe` to fail closed even when each individual batch obfuscated
successfully.

Confirmed with:

```powershell
.venv\Scripts\python.exe obfuscator.py obfuscate `
  sample_sql/07_multiple_batches.sql `
  --workspace <temp-workspace> `
  --llm-safe
```

Observed result:

```text
Error: LLM-safe validation failed: The privacy audit could not parse the obfuscated output for a full identifier-surface check.
```

Recommended action:

- Resolved on 2026-05-31: the privacy audit now parses each dialect-profile
  batch independently before combining statements for surface analysis.
- Added a CLI regression test for multi-batch T-SQL with `--llm-safe`.

### 2. Resolved: tutorial strict-`GO` failure example did not fail

`docs/COMMAND_TUTORIAL.md:792-817` previously presented this as an invalid
strict case:

```sql
SELECT 1; GO
SELECT 2;
```

The implementation only rejects lines that start with `GO` but are not
standalone separators (`src/sql_obfuscator/pipeline.py:121-126`). The previous
documented example therefore did not trigger strict validation.

Resolution:

- Resolved on 2026-05-31: replaced the invalid example with:

```sql
SELECT 1;
GO -- separator comment
SELECT 2;
```

### 3. Resolved: the "Current State" recreation spec was outdated

`specs/specs_2026_02_18.md` previously labeled itself as the current state, but
its preserved historical body no longer matches the codebase. Examples:

- `specs/specs_2026_02_18.md:35-36` documents legacy invocation and only four
  subcommands.
- `specs/specs_2026_02_18.md:61-64` documents legacy CLI fallback that no
  longer exists.
- `specs/specs_2026_02_18.md:77` says `--strict-go` is a no-op.
- `specs/specs_2026_02_18.md:130-136` describes animal-only generated names,
  while the current generator uses adjective-animal combinations.

The current CLI includes `obfuscate`, `deobfuscate`, `validate-before-write`,
`apply-llm-edits`, `roundtrip`, `translate`, and `workspace-info`.

Resolution:

- Resolved on 2026-05-31: relabeled the dated recreation spec as a historical
  snapshot and added a warning that directs readers to maintained usage docs,
  current source, and tests for the live contract.

### 4. Medium: `use cases.md` needs bounded-edit guardrails

`use cases.md` suggests broad LLM rewrites such as alias standardization,
splitting scripts, CTE restructuring, and statement reordering. Those are
reasonable expert-mode use cases, but they conflict with the recommended
bounded-edit workflow described in `docs/COMMAND_TUTORIAL.md:314-370`.

Recommended action:

- Separate analysis-only use cases from edit-producing use cases.
- Mark structural rewrites and alias changes as expert-mode workflows.
- Point edit-producing workflows to `apply-llm-edits`.

### 5. Low: redaction policy documentation is incomplete

`README.md:266` and `docs/COMMAND_TUTORIAL.md:408` list
`all|strings-only|sensitive`, but do not fully define their behavior.

The implementation in `src/sql_obfuscator/redaction.py:190-194` behaves as
follows:

- `all`: redact strings and numeric literals, except structural datatype
  parameters.
- `strings-only`: redact only string literals.
- `sensitive`: redact literals in configured sensitive-column contexts.

The workspace artifact description also needs a nuance: `redaction.json` and
`redaction.schema.json` are written only when reversible redaction generates at
least one literal placeholder (`src/sql_obfuscator/redaction.py:98-104`), not
merely whenever reversible mode is selected.

Recommended action:

- Add a compact policy table to `README.md` and the tutorial.
- Clarify the conditional creation of reversible redaction artifacts.

### 6. Low: integrity documentation is incomplete

`README.md:245` says integrity failures affect `deobfuscate`, `roundtrip`, and
`workspace-info`.

Existing workspace snapshots are also loaded and integrity-checked by:

- `apply-llm-edits` (`src/sql_obfuscator/cli.py:551`)
- `validate-before-write` through the shared deobfuscation pipeline
  (`src/sql_obfuscator/cli.py:636-638`)

`roundtrip` normally creates and immediately reloads a fresh workspace, rather
than consuming an existing workspace.

Recommended action:

- Update the integrity section to distinguish commands that validate existing
  workspaces from `roundtrip`, which validates the fresh workspace it creates.

### 7. Low: installation dependency constraints differ

`README.md:24` recommends:

```bash
pip install -e .
```

However:

- `pyproject.toml:12` declares `sqlglot>=26.0.0`
- `requirements.txt:1` declares `sqlglot>=28,<29`

CI installs the editable package through `pip install -e .[dev]`, so it uses
the broader dependency constraint.

Recommended action:

- Align `pyproject.toml` with the supported runtime range, or
- Document why the optional `requirements.txt` constraint is stricter.

### 8. Low: `TODOs.md` contains completed items

`TODOs.md` still lists prompt preparation, LLM instructions, use-case work, and
stress tests as open-ended TODOs. The current codebase already includes
generated `llm_instructions.md`, structured `apply-llm-edits`, a use-case
document, and a broad fixture/test corpus.

Recommended action:

- Remove completed entries.
- Rewrite remaining entries as scoped work items or link them to issues.

## Environment Note

The checked-in source currently exposes `apply-llm-edits`, but the installed
`.venv\Scripts\sql-obfuscator.exe` entry point in the audited environment came
from an older editable install and did not expose that command. Running the
wrapper script (`python obfuscator.py`) loaded the checked-in source correctly.

Recommended action:

- Reinstall the editable package before validating the installed entry point:

```powershell
.venv\Scripts\python.exe -m pip install -e .
```

## Verification

The existing automated checks pass:

```powershell
.venv\Scripts\pytest.exe -q
.venv\Scripts\pytest.exe tests/test_docs_consistency.py -q
```

The current docs consistency test checks a limited flag subset and does not
cover the behavior-level mismatches above.
