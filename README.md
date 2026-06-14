# SQL Obfuscator

Python CLI tool for preparing SQL for local review, external LLM review, restoration after
LLM-assisted edits, and T-SQL/Hive translation.

Use it when you need to:

- create SQL and instructions that are safer to send to an external LLM
- restore original identifiers and reversible-redaction placeholders after LLM edits
- hide table names, column names, CTE names, aliases, temp-table names, and supported
  qualifiers
- translate SQL between T-SQL and Hive

## Installation

```bash
pip install -e .
```

The installed command is:

```bash
sql-obfuscator --help
```

Commands below use the repository wrapper so they also work during development:

```bash
python obfuscator.py --help
```

## Choose Your Goal

| Goal | Start here |
|---|---|
| Send SQL to an external LLM | [Prepare SQL for an external LLM](#prepare-sql-for-an-external-llm) |
| Restore structured LLM edits | [Restore LLM-edited SQL](#restore-llm-edited-sql) |
| Replace identifiers locally | [Basic obfuscation](#basic-obfuscation) |
| Translate between T-SQL and Hive | [Translate SQL](#translate-sql) |

For worked examples, see [the command tutorial](docs/guides/command-tutorial.md). For every
flag, see [the command reference](docs/reference/cli.md).

## Prepare SQL For An External LLM

Use the workflow command before sending SQL outside your environment:

```bash
python obfuscator.py prepare-for-llm script.sql
```

This creates a local workspace and applies the recommended external-sharing defaults:

- identifier obfuscation
- custom schema and catalog/database qualifier obfuscation on supported references
- reversible literal redaction
- comment stripping
- fail-closed validation

`prepare-for-llm` defaults to reversible redaction so edited SQL can be restored with
original literal values later.

If the command succeeds, send only:

- `script.obf/obfuscated.sql`
- `script.obf/llm_instructions.md`

Do not send the entire workspace. It contains the original SQL, mappings, and local
restoration metadata.

Useful options:

| Option | Use it when |
|---|---|
| `--irreversible` | Original literal values do not need to be restored later. |
| `--expert-mode` | You intend to manually review output that automatic validation cannot approve. |
| `--print-sql` | You explicitly want the obfuscated SQL printed after the workflow summary. |

`prepare-for-llm` does not call an LLM. You send the generated files to your chosen LLM and
save the returned JSON locally.

## Restore LLM-Edited SQL

For LLM-assisted edits, use the structured statement-replacement format described in
`script.obf/llm_instructions.md`. Each edit targets a known statement ID and leaves
unrelated statements untouched.

After the LLM returns JSON, save it locally as:

```text
script.obf/llm_edits.json
```

Then run:

```bash
python obfuscator.py restore-from-llm \
  --workspace script.obf \
  --edits script.obf/llm_edits.json
```

This applies the edit JSON, writes `script.obf/llm_response_obfuscated.sql`, validates
restoration, and writes `script.obf/deobfuscated.sql` only when validation passes.

Use a dry run to check the workflow without writing derived outputs:

```bash
python obfuscator.py restore-from-llm \
  --workspace script.obf \
  --edits script.obf/llm_edits.json \
  --dry-run
```

Lower-level `obfuscate`, `apply-llm-edits`, `deobfuscate`, and `validate-before-write`
commands remain available for custom workflows and direct edited-SQL restoration.

For the full workflow, redaction choices, and safety checks, read
[Sharing SQL With an External LLM](docs/guides/llm-sharing.md).

## Basic Obfuscation

```bash
python obfuscator.py obfuscate script.sql
```

This writes:

- `script_obfuscated.sql`: SQL with generated identifier names
- `script.obf/`: a local workspace used for later validation or restoration

This baseline command is suitable for local use. It does not remove comments or redact
literal values unless you pass explicit redaction options.

Use a seed when you want repeatable generated names:

```bash
python obfuscator.py obfuscate script.sql --seed 42
```

## Translate SQL

```bash
python obfuscator.py translate \
  --input script.sql \
  --source-dialect tsql \
  --target-dialect hive \
  --validate
```

Translation is structural conversion through `sqlglot`. Parsing successfully does not prove
that the translated SQL has identical behavior on the target database.

## Workspaces

Most commands create or use a workspace such as `script.obf/`. A workspace stores the
original SQL, obfuscated SQL, mappings needed for restoration, generated LLM instructions,
redaction metadata when reversible redaction is used, and diagnostic reports.

Treat the workspace as sensitive local data. See
[Workspaces and Reports](docs/reference/workspaces-and-reports.md) for its file layout and
integrity checks.

## Documentation

- [Documentation Index](docs/README.md): all guides, reference material, and maintainer notes
- [Sharing SQL With an External LLM](docs/guides/llm-sharing.md): recommended and expert LLM workflows
- [Command Tutorial](docs/guides/command-tutorial.md): worked examples for common tasks
- [Command Reference](docs/reference/cli.md): commands, flags, output modes, and exit behavior
- [Workspaces and Reports](docs/reference/workspaces-and-reports.md): workspace files, reports, and integrity checks
- [Troubleshooting](docs/guides/troubleshooting.md): common failures and recovery steps
- [Python Workflow API](docs/reference/python-api.md): in-process integration API
- [LLM Use Cases](docs/guides/use-cases.md): appropriate tasks and workflow selection

## Current Limits

- Some advanced procedural T-SQL constructs cannot be fully transformed. The tool may copy
  those statements through without full obfuscation and print a parser fallback notice.
- Use `prepare-for-llm` before external sharing. It rejects statements copied through
  without full obfuscation and known higher-risk visible names, but it is not a complete
  confidentiality guarantee.
- Qualifier obfuscation covers qualifier names, not function names. User-defined or unknown
  function names may still remain visible.
- Boolean and `NULL` tokens are not redacted. Numeric datatype parameters such as
  `NUMERIC(10,2)` are intentionally preserved.
- SQL formatting and comments can change during regeneration.
- The tool targets identifier restoration, not byte-for-byte source reconstruction.
- A translated script may parse successfully but still behave differently on the target
  database. Test it before production use.

## Development

```bash
pip install -e .[dev]
pytest
```

The code and documentation in this repository were largely written by GPT-5.3 and later
models.
