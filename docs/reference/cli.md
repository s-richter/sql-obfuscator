# Command Reference

This page lists the CLI commands, flags, output behavior, and common flag constraints.
For step-by-step examples, see [the command tutorial](../guides/command-tutorial.md).

## Invocation

During repository development:

```bash
python obfuscator.py <command> [options]
```

After installation:

```bash
sql-obfuscator <command> [options]
```

Available commands:

| Command | Purpose |
|---|---|
| `prepare-for-llm` | Create LLM-sharing artifacts with recommended workflow defaults |
| `restore-from-llm` | Apply bounded LLM edits, validate, and restore SQL |
| `obfuscate` | Replace identifiers and create a workspace |
| `apply-llm-edits` | Apply structured statement replacements returned by an LLM |
| `deobfuscate` | Restore identifiers in edited obfuscated SQL |
| `validate-before-write` | Restore SQL and write output only when validation passes |
| `roundtrip` | Obfuscate and immediately restore SQL for verification |
| `translate` | Convert SQL between supported dialects |
| `workspace-info` | Validate and summarize an existing workspace |

## `obfuscate`

```bash
python obfuscator.py obfuscate <input.sql|-> [options]
```

Use `-` instead of a filename to read SQL from stdin.

### Options

| Option | Behavior |
|---|---|
| `--workspace <dir>` | Workspace folder. Defaults to `<input-stem>.obf` or `stdin.obf`. |
| `--dialect <tsql|hive>` | SQL dialect. Defaults to `tsql`. |
| `--seed <int>` | Use repeatable generated names. |
| `--pretty` / `--no-pretty` | Enable or disable formatted SQL output. Formatting is enabled by default. |
| `--strict-go` | Reject T-SQL lines that start with `GO` but are not standalone batch separators. |
| `--instruction-template <path>` | Replace the generated `llm_instructions.md` content with a custom Markdown template. |
| `--strip-comments` | Remove SQL comments from generated SQL. Requires a redaction mode. |
| `--redact-literals` | Sanitize string and numeric values. Requires a redaction mode. |
| `--redaction-mode <none|irreversible|reversible>` | Choose how literal and comment sanitization works. Defaults to `none`. |
| `--redaction-policy <all|strings-only|sensitive>` | Choose which literal values are sanitized. Defaults to `all`. |
| `--redaction-sensitive-columns <csv>` | Comma-separated columns used by the `sensitive` policy. |
| `--obfuscate-qualifiers` | Obfuscate custom schema qualifiers and catalog/database qualifiers on table references, column references, and qualified function calls. |
| `--stdout-only` | Print SQL without writing the sibling output file. The workspace is still written. |
| `--output-dir <dir>` | Write the generated SQL file into a specific directory. File input only. |
| `--llm-safe` / `--no-llm-safe` | Stop when known higher-risk content remains in SQL intended for external sharing. Disabled by default. |

### Redaction Flag Rules

- `--strip-comments` and `--redact-literals` require
  `--redaction-mode irreversible` or `--redaction-mode reversible`.
- `--redaction-policy sensitive` requires `--redaction-sensitive-columns`.
- `--redaction-sensitive-columns` cannot be used with another policy.

### Output

For file input such as `script.sql`, the default generated SQL file is:

```text
script_obfuscated.sql
```

The default workspace is:

```text
script.obf/
```

`obfuscate` also prints generated SQL to stdout. `--stdout-only` suppresses only the sibling
SQL file write, not stdout or workspace creation.

When `--llm-safe` rejects a script, the workspace is still written for local inspection but
the sibling SQL output file is not written. See
[Sharing SQL With an External LLM](../guides/llm-sharing.md).

## `prepare-for-llm`

```bash
python obfuscator.py prepare-for-llm <input.sql|-> [options]
```

This workflow command prepares the intended files for an external LLM. It applies the
recommended external-sharing defaults:

- reversible redaction
- literal redaction
- comment stripping
- qualifier obfuscation
- fail-closed validation

Use `-` instead of a filename to read SQL from stdin.

### Options

| Option | Behavior |
|---|---|
| `--workspace <dir>` | Workspace folder. Defaults to `<input-stem>.obf` or `stdin.obf`. |
| `--dialect <tsql|hive>` | SQL dialect. Defaults to `tsql`. |
| `--seed <int>` | Use repeatable generated names. |
| `--instruction-template <path>` | Replace the generated `llm_instructions.md` content with a custom Markdown template. |
| `--irreversible` | Use irreversible redaction instead of the default reversible redaction. |
| `--expert-mode` | Allow output that requires manual review instead of failing closed. |
| `--print-sql` | Print obfuscated SQL after the workflow summary. |

### Output

For file input such as `script.sql`, the default workspace is:

```text
script.obf/
```

The command writes the workspace artifacts, including:

```text
script.obf/obfuscated.sql
script.obf/llm_instructions.md
script.obf/reports/privacy_summary.json
script.obf/reports/llm_workflow_report.json
```

By default, it does not write a sibling `script_obfuscated.sql` file and does not print SQL
to stdout. It prints a summary pointing to the files to send.

The workflow defaults to reversible redaction so original literal values can be restored
after LLM edits. Use `--irreversible` when original literal values do not need to be
restored.

### Exit Behavior

- exit `0` when validation passes
- exit `1` when fail-closed validation finds blockers
- exit `0` with `--expert-mode` when blockers exist, after writing reports and marking the
  output as requiring manual review

Use lower-level `obfuscate` when you need custom redaction policy, `--stdout-only`,
`--output-dir`, or other fine-grained output controls.

## `apply-llm-edits`

```bash
python obfuscator.py apply-llm-edits \
  --workspace <dir> \
  --edits <llm_edits.json> \
  [options]
```

This command applies structured statement replacements to `obfuscated.sql`. It preserves
untouched statements exactly.

### Options

| Option | Behavior |
|---|---|
| `--workspace <dir>` | Workspace created by `obfuscate`. Required. |
| `--edits <path>` | JSON edit payload returned by the LLM. Required. |
| `--out <path>` | Output path. Defaults to `<workspace>/llm_response_obfuscated.sql`. |
| `--dry-run` | Validate and summarize edits without writing files. |

The edit file may contain raw JSON or a fenced `json` block. Required format:

```json
{
  "schema_version": 1,
  "format": "statement_replacements",
  "edits": [
    {
      "statement_id": "stmt_0001",
      "sql": "SELECT generated_column FROM generated_table"
    }
  ]
}
```

Each replacement must target a known statement ID and contain exactly one SQL statement.
The generated names in the example are illustrative; copy the exact names from your
`obfuscated.sql`. The default output cannot overwrite workspace `obfuscated.sql`.

## `restore-from-llm`

```bash
python obfuscator.py restore-from-llm \
  --workspace <dir> \
  --edits <llm_edits.json> \
  [options]
```

This workflow command applies structured bounded edit JSON, validates restoration, and
writes restored SQL only when checks pass or are explicitly overridden.

### Options

| Option | Behavior |
|---|---|
| `--workspace <dir>` | Workspace created by `prepare-for-llm` or `obfuscate`. Required. |
| `--edits <path>` | JSON edit payload returned by the LLM. Required. |
| `--out <path>` | Restored output path. Defaults to `<workspace>/deobfuscated.sql`. |
| `--dry-run` | Validate edits and restoration safety without writing workflow outputs. |
| `--allow-unresolved` | Write output despite unresolved findings. |
| `--allow-low-confidence` | Write output despite low-confidence findings. |

`restore-from-llm` accepts structured edit JSON only. Use `validate-before-write` or
`deobfuscate` when you need to restore a full edited obfuscated SQL file.

### Output

On success, the workflow writes:

```text
<workspace>/llm_response_obfuscated.sql
<workspace>/deobfuscated.sql
```

It prints artifact paths and validation status, not the restored SQL body.

`--out <path>` controls the final restored SQL path. The workspace still receives
de-obfuscation reports and the applied obfuscated response remains at the workspace default
path.

### Exit Behavior

- exit `0` when edit application and restoration validation pass
- exit `1` when the edit payload is invalid
- exit `1` when unresolved findings exist without `--allow-unresolved`
- exit `1` when low-confidence findings exist without `--allow-low-confidence`
- with `--dry-run`, exit `0` when the workflow would be restorable and exit `1` when it
  would have unresolved or low-confidence findings

## `deobfuscate`

```bash
python obfuscator.py deobfuscate \
  --workspace <dir> \
  --input <edited-obfuscated.sql> \
  [options]
```

### Options

| Option | Behavior |
|---|---|
| `--workspace <dir>` | Workspace created by `obfuscate`. Required. |
| `--input <path>` | Edited obfuscated SQL. Required. |
| `--out <path>` | Restored output path. Defaults to `<workspace>/deobfuscated.sql`. |
| `--dry-run` | Print restoration diagnostics without writing restored SQL or reports. |
| `--allow-unresolved` | Write output despite unresolved or ambiguous names and unresolved reversible-redaction placeholders. |
| `--allow-low-confidence` | Write output despite low-confidence restoration matches. |

### Validation Terms

| Term | Meaning |
|---|---|
| unknown | A generated identifier or placeholder is not recognized. |
| ambiguous | More than one restoration target is possible. |
| low-confidence | A likely restoration match exists, but structural edits reduced confidence. |

### Exit Behavior

For `--dry-run`:

- exit `0` when no unresolved names or placeholders are found
- exit `1` when unresolved names or placeholders are found

For normal output:

- exit `0` when restoration checks pass
- exit `1` when unresolved findings exist without `--allow-unresolved`
- exit `1` when low-confidence findings exist without `--allow-low-confidence`

## `validate-before-write`

```bash
python obfuscator.py validate-before-write \
  --workspace <dir> \
  --input <edited-obfuscated.sql> \
  [options]
```

This lower-level command runs validation first and writes restored SQL only when checks pass
or are explicitly overridden. Use it when you already have a full edited obfuscated SQL file
instead of structured edit JSON.

### Options

| Option | Behavior |
|---|---|
| `--workspace <dir>` | Workspace created by `obfuscate`. Required. |
| `--input <path>` | Edited obfuscated SQL. Required. |
| `--out <path>` | Restored output path. Defaults to `<workspace>/deobfuscated.sql`. |
| `--allow-unresolved` | Write output despite unresolved findings. |
| `--allow-low-confidence` | Write output despite low-confidence findings. |

Use override flags only after manual review.

## `roundtrip`

```bash
python obfuscator.py roundtrip <input.sql|-> [options]
```

`roundtrip` obfuscates and immediately restores SQL so you can verify a script before using
it in a larger workflow. It accepts all `obfuscate` options plus:

| Option | Behavior |
|---|---|
| `--diff-report` | Write `reports/roundtrip_diff.txt`. |

The workspace also receives normalized comparison files:

- `reports/original_pretty.sql`
- `reports/deobfuscated_pretty.sql`
- `reports/roundtrip_normalized_diff.txt`
- `reports/roundtrip_report.json`

The command exits non-zero when unresolved or low-confidence restoration findings exist.

## `translate`

```bash
python obfuscator.py translate \
  --input <input.sql|-> \
  --source-dialect <tsql|hive> \
  --target-dialect <tsql|hive> \
  [options]
```

### Options

| Option | Behavior |
|---|---|
| `--input <path|->` | SQL file or `-` for stdin. Required. |
| `--source-dialect <tsql|hive>` | Parser dialect. Required. |
| `--target-dialect <tsql|hive>` | Output dialect. Required. |
| `--out <path>` | Explicit translated SQL output path. |
| `--pretty` / `--no-pretty` | Enable or disable formatting. Formatting is enabled by default. |
| `--validate` | Parse generated SQL in the target dialect and fail on parse errors. |
| `--workspace <dir>` | Write `reports/translation_report.json`. |
| `--report-only` | Print summary and optional report without writing translated SQL. |
| `--stdout-only` | Print translated SQL without writing SQL files. |
| `--output-dir <dir>` | Write translated SQL into a specific directory. File input only. |

### Output Rules

| Mode | Behavior |
|---|---|
| Default file input | Write `<input-stem>_<target-dialect>.sql`. |
| `--out <path>` | Write the explicit path. |
| `--output-dir <dir>` | Write the default generated filename in the selected directory. |
| `--stdout-only` | Print summary and SQL; write no translated SQL file. |
| `--report-only` | Print summary; write no translated SQL file. |
| Stdin without another output-mode flag | Print summary and SQL. |

When `--workspace <dir>` is used and translation output is not suppressed or redirected with
`--out`, the workspace also stores `translated.sql`.

Invalid combinations:

- `--stdout-only` with `--out`
- `--stdout-only` with `--output-dir`
- `--stdout-only` with `--report-only`
- `--out` with `--output-dir`

Translation is structural conversion through `sqlglot`. Generated SQL may parse successfully
but still behave differently on the target database. Test it before production use.

## `workspace-info`

```bash
python obfuscator.py workspace-info --workspace <dir>
```

This validates workspace integrity and prints:

- dialect, seed, formatting mode, batch count, and statement count
- identifier mapping counts
- tracked-file count
- presence of generated files and reports
- privacy summary flags when available

## Stdin Examples

PowerShell:

```powershell
Get-Content script.sql | python obfuscator.py obfuscate -
Get-Content script.sql | python obfuscator.py prepare-for-llm -
Get-Content script.sql | python obfuscator.py roundtrip - --diff-report
Get-Content script.sql | python obfuscator.py translate --input - --source-dialect tsql --target-dialect hive
```

POSIX shell:

```bash
cat script.sql | python obfuscator.py obfuscate -
cat script.sql | python obfuscator.py prepare-for-llm -
cat script.sql | python obfuscator.py roundtrip - --diff-report
cat script.sql | python obfuscator.py translate --input - --source-dialect tsql --target-dialect hive
```

## Related Documents

- [Command Tutorial](../guides/command-tutorial.md)
- [Sharing SQL With an External LLM](../guides/llm-sharing.md)
- [Workspaces and Reports](workspaces-and-reports.md)
- [Troubleshooting](../guides/troubleshooting.md)
