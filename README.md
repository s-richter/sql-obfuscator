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

For worked examples, see [the command tutorial](docs/COMMAND_TUTORIAL.md). For every flag,
see [the command reference](docs/COMMAND_REFERENCE.md).

## Basic Obfuscation

```bash
python obfuscator.py obfuscate script.sql
```

This writes:

- `script_obfuscated.sql`: SQL with generated identifier names
- `script.obf/`: a local workspace used for later validation or restoration (for details about workspaces see below)

The tool replaces identifiers such as table names, column names, CTE names, aliases, and
temp-table names. It does not replace string values, numeric values, comments, variables,
function names, or schema qualifiers unless you enable the relevant sanitizing options.

Use a seed when you want repeatable generated names:

```bash
python obfuscator.py obfuscate script.sql --seed 42
```

## Share SQL With an External LLM

Use this command before sending SQL outside your environment:

```bash
python obfuscator.py obfuscate script.sql \
  --llm-safe \
  --redaction-mode irreversible \
  --redact-literals \
  --strip-comments
```

This replaces identifiers, removes comments, and sanitizes string and numeric values.
`--llm-safe` adds a final check. It stops with an error when the tool cannot confirm that
the generated SQL is suitable for the recommended external-sharing workflow. For example,
it rejects statements that could not be fully obfuscated and higher-risk names that remain
visible.

Important: `--llm-safe` is a validation check, not a redaction preset. Use
`--redact-literals` and `--strip-comments` when preparing SQL for sharing.

If the command succeeds, send only:

- `script.obf/obfuscated.sql`
- `script.obf/llm_instructions.md`

Do not send the entire workspace. It contains the original SQL and restoration metadata.

For the full workflow, redaction choices, and an explanation of safety errors, read
[Sharing SQL With an External LLM](docs/LLM_SHARING.md).

## Restore Edited SQL

For LLM-assisted edits, ask the model to return the structured statement replacements
described in `script.obf/llm_instructions.md`. Then apply, check, and restore the result:

```bash
python obfuscator.py apply-llm-edits \
  --workspace script.obf \
  --edits script.obf/llm_edits.json

python obfuscator.py deobfuscate \
  --workspace script.obf \
  --input script.obf/llm_response_obfuscated.sql \
  --dry-run

python obfuscator.py validate-before-write \
  --workspace script.obf \
  --input script.obf/llm_response_obfuscated.sql
```

The dry run checks whether names can still be restored reliably. The final command writes
`script.obf/deobfuscated.sql` only when validation passes.

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

Treat the workspace as sensitive local data. See [Workspaces and Reports](docs/WORKSPACES.md)
for its file layout and integrity checks.

## Documentation

- [Sharing SQL With an External LLM](docs/LLM_SHARING.md): privacy guidance and edit workflow
- [Command Tutorial](docs/COMMAND_TUTORIAL.md): worked examples for common tasks
- [Command Reference](docs/COMMAND_REFERENCE.md): commands, flags, output modes, and exit behavior
- [Workspaces and Reports](docs/WORKSPACES.md): workspace files, reports, and integrity checks
- [Troubleshooting](docs/TROUBLESHOOTING.md): common failures and recovery steps
- [Python Workflow API](docs/PYTHON_API.md): in-process integration API
- [LLM Use Cases](use%20cases.md): appropriate tasks and workflow selection

## Current Limits

- Some advanced procedural T-SQL constructs cannot be fully transformed. The tool may preserve
  those statements and print a parser-fallback notice.
- Use `--llm-safe` before external sharing. It rejects preserved statements and known
  higher-risk visible names, but it is not a complete confidentiality guarantee.
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
