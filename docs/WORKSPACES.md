# Workspaces And Reports

Most obfuscation workflows use a local workspace. This guide explains what the workspace is,
which files it contains, and which files must remain private.

## What Is A Workspace?

A workspace is the run folder created by `obfuscate` or `roundtrip`. For `script.sql`, the
default workspace is:

```text
script.obf/
```

It stores:

- the original SQL
- generated obfuscated SQL
- identifier mappings used for restoration
- generated instructions for an external LLM
- optional literal-restoration metadata
- diagnostic reports

Treat the workspace as sensitive local data. Do not send the entire folder to an external
LLM.

## Files To Share With An External LLM

After successful `obfuscate --llm-safe`, send only:

```text
script.obf/obfuscated.sql
script.obf/llm_instructions.md
```

Keep every other workspace file local unless you have reviewed it for your specific use
case.

## Typical File Layout

```text
script.obf/
|-- original.sql
|-- obfuscated.sql
|-- llm_instructions.md
|-- mapping.json
|-- mapping.schema.json
|-- context.json
|-- context.schema.json
|-- integrity.json
|-- integrity.schema.json
|-- redaction.json                         # reversible redaction only, when placeholders exist
|-- redaction.schema.json                  # reversible redaction only, when placeholders exist
|-- llm_response_obfuscated.sql            # after apply-llm-edits, by default
|-- deobfuscated.sql                       # after successful restoration
|-- translated.sql                         # after translate --workspace, in applicable output modes
`-- reports/
    |-- privacy_summary.json
    |-- privacy_summary.schema.json
    |-- llm_workflow_report.json
    |-- llm_workflow_report.schema.json
    |-- llm_edit_application_report.json   # after apply-llm-edits
    |-- llm_edit_application_report.schema.json
    |-- deobfuscation_report.json          # after restoration
    |-- coverage_report.txt                # after restoration
    |-- roundtrip_report.json              # after roundtrip
    |-- roundtrip_diff.txt                 # after roundtrip --diff-report
    |-- original_pretty.sql                # after roundtrip
    |-- deobfuscated_pretty.sql            # after roundtrip
    |-- roundtrip_normalized_diff.txt      # after roundtrip
    |-- translation_report.json            # after translate --workspace
    `-- translation_report.schema.json
```

Some files are created only after the relevant command runs.

## Core Files

| File | Purpose |
|---|---|
| `original.sql` | Original input. Always sensitive. |
| `obfuscated.sql` | Generated SQL intended for inspection or approved sharing. |
| `llm_instructions.md` | Instructions for small, structured LLM edits. |
| `mapping.json` | Identifier lookup data used to restore original names. Always sensitive. |
| `context.json` | Run settings and statement metadata used during restoration. |
| `integrity.json` | SHA-256 checksums for protected workspace files. |
| `redaction.json` | Original literal values for reversible redaction. Always sensitive. |
| `llm_response_obfuscated.sql` | Edited obfuscated SQL, usually created by `apply-llm-edits`. |
| `deobfuscated.sql` | Restored final SQL. |
| `translated.sql` | Workspace copy of translated SQL in applicable translation output modes. |

## Reports

### `privacy_summary.json`

Written during obfuscation. This is the first report to inspect when `--llm-safe` rejects a
script.

It contains:

- whether external-sharing approval was blocked
- whether manual review is recommended
- fallback-preserved statement count
- visible higher-risk name classes
- occurrence counts and examples
- privacy-audit parse errors, when applicable

See [Sharing SQL With an External LLM](LLM_SHARING.md) for interpretation.

### `llm_workflow_report.json`

Written during obfuscation and updated after restoration.

It summarizes:

- whether `--llm-safe` was requested
- whether external-sharing approval passed
- transformed and fallback-preserved statement counts
- visible privacy warning and blocker counts
- literal redaction counts
- later unresolved, ambiguous, and low-confidence restoration counts

### `llm_edit_application_report.json`

Written by `apply-llm-edits`.

It records:

- number of applied edits
- number of untouched statements
- total statements
- targeted statement IDs

### `deobfuscation_report.json`

Written after successful non-dry-run restoration.

It records identifier restoration results, statement matching diagnostics, recommendations,
and reversible-redaction placeholder results when applicable.

### Roundtrip Reports

`roundtrip` writes a normalized comparison set:

- `roundtrip_report.json`
- `original_pretty.sql`
- `deobfuscated_pretty.sql`
- `roundtrip_normalized_diff.txt`

With `--diff-report`, it also writes `roundtrip_diff.txt`.

### Translation Report

`translate --workspace <dir>` writes `translation_report.json` with translation and optional
target-dialect validation results.

## Statement IDs

`context.json` records metadata for each statement, including IDs such as:

```text
stmt_0001
stmt_0002
```

The documentation calls these **statement anchors**. They help the tool associate edited SQL
with the original obfuscated statements. Generated `llm_instructions.md` lists the IDs and
asks an external LLM to return targeted statement replacements.

Prefer `apply-llm-edits` over manual full-file editing. It uses statement IDs to preserve
untouched statements exactly.

## Integrity Checks

The workspace protects key files with SHA-256 checksums in `integrity.json`.

Tracked files:

- `original.sql`
- `obfuscated.sql`
- `mapping.json`
- `context.json`
- `redaction.json`, when reversible-redaction metadata exists

Commands that load an existing workspace validate these checksums. If a protected file
changes after workspace creation, regenerate the workspace from trusted input instead of
editing checksum files.

## Inspect A Workspace

```bash
python obfuscator.py workspace-info --workspace script.obf
```

This validates integrity and prints:

- run settings
- batch, statement, and mapping counts
- tracked-file count
- artifact and report availability
- privacy summary state

## Related Documents

- [Sharing SQL With an External LLM](LLM_SHARING.md)
- [Command Reference](COMMAND_REFERENCE.md)
- [Troubleshooting](TROUBLESHOOTING.md)
