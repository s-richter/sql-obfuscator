# SQL Identifier Obfuscator

Python CLI tool for replacing SQL identifiers with generated names while preserving SQL
structure. It supports T-SQL and Hive, can restore the original identifiers after editing,
and can translate SQL between the supported dialects.

Use it when you need to:

- hide table names, column names, CTE names, aliases, and temp-table names
- send a sanitized SQL script to an external LLM for review or small edits
- restore original identifiers after an LLM-assisted edit
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

| Goal                             | Start here                                                        |
| -------------------------------- | ----------------------------------------------------------------- |
| Replace identifiers locally      | [Basic obfuscation](#basic-obfuscation)                           |
| Send SQL to an external LLM      | [Share SQL with an external LLM](#share-sql-with-an-external-llm) |
| Restore an LLM-edited script     | [Restore edited SQL](#restore-edited-sql)                         |
| Translate between T-SQL and Hive | [Translate SQL](#translate-sql)                                   |

For worked examples, see [the command tutorial](docs/guides/command-tutorial.md). For every
flag, see [the command reference](docs/reference/cli.md).

## Basic Obfuscation

```bash
python obfuscator.py obfuscate script.sql
```

This writes:

- `script_obfuscated.sql`: SQL with generated identifier names
- `script.obf/`: a local workspace used for later validation or restoration (for details about workspaces see below)

The tool replaces identifiers such as table names, column names, CTE names, aliases, and
temp-table names. It does not replace string values, numeric values, comments, variables,
or function names. Custom schema and catalog/database qualifiers on table references,
column references, and qualified function calls can be obfuscated with
`--obfuscate-qualifiers`.

Use a seed when you want repeatable generated names:

```bash
python obfuscator.py obfuscate script.sql --seed 42
```

## Share SQL With an External LLM

Use this command before sending SQL outside your environment:

```bash
python obfuscator.py prepare-for-llm script.sql
```

This replaces identifiers, obfuscates custom schema and catalog/database qualifiers on table
references, column references, and qualified function calls, removes comments, redacts string
and numeric values, and runs fail-closed validation. `prepare-for-llm` defaults to reversible
redaction so edited SQL can be restored with original literal values later.

| Flag | Purpose |
| ---- | ------- |
| `--irreversible` | Use one-way redaction when original literal values do not need to be restored. |
| `--expert-mode` | Allow output that automatic validation cannot approve; review generated reports before sharing. |
| `--print-sql` | Print obfuscated SQL to stdout after the workflow summary. |

For custom redaction policies or unusual output modes, use the lower-level `obfuscate`
command with explicit flags.

If the command succeeds, send only:

- `script.obf/obfuscated.sql`
- `script.obf/llm_instructions.md`

Do not send the entire workspace. It contains the original SQL and restoration metadata.

For the full workflow, redaction choices, and an explanation of safety errors, read
[Sharing SQL With an External LLM](docs/guides/llm-sharing.md).

## Restore Edited SQL

For LLM-assisted edits, ask the model to return the structured statement replacements
described in `script.obf/llm_instructions.md`. Then restore the result:

```bash
python obfuscator.py restore-from-llm \
  --workspace script.obf \
  --edits script.obf/llm_edits.json
```

This applies the structured statement-replacement JSON, where each edit targets a known
statement ID and leaves unrelated statements untouched. The command writes
`script.obf/llm_response_obfuscated.sql`, validates restoration, and writes
`script.obf/deobfuscated.sql` only when validation passes. Use `restore-from-llm --dry-run`
to validate the full workflow without writing derived outputs.

Lower-level `apply-llm-edits`, `deobfuscate`, and `validate-before-write` commands remain
available for custom workflows and direct edited-SQL restoration.

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
and diagnostic reports.

Treat the workspace as sensitive local data. See
[Workspaces and Reports](docs/reference/workspaces-and-reports.md) for its file layout and
integrity checks.

## Documentation

- [Documentation Index](docs/README.md): all guides, reference material, and maintainer notes
- [Sharing SQL With an External LLM](docs/guides/llm-sharing.md): privacy guidance and edit workflow
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
- `--obfuscate-qualifiers` covers qualifier names, not function names. User-defined or
  unknown function names may still remain visible.
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
