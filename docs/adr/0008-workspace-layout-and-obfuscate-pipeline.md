---
status: accepted
---
# A workspace sits next to its script, and `obfuscate` formats before it replaces

A workspace is a folder named after the script's stem with `.obf` appended (`report.sql` gets `report.obf/` next to it). The first `obfuscate` creates it; every later command is given its path. `obfuscate` always formats first, then replaces comments with markers, then names and values, and it writes the formatted script, the obfuscated script and the report side by side. There is no way to skip formatting; `format` exists to look at the formatted script without creating a workspace. We settled this because the round-trip check is defined against the formatted script, so the formatted script must be exactly the text the obfuscated script was made from, and because decision record 0006 says output goes to the workspace only but never said what the workspace contains.

Comments are replaced after formatting, not before, because sqlglot's formatter turns line comments into block comments and moves them to the end of the line. Markers placed before formatting would move with them, and the formatted script would no longer match what the user wrote plus layout.

## Layout

```
report.obf/
  mapping.json      every replacement in both directions; as sensitive as the originals
  settings.json     dialect, seed, strings, comments; written on first use
  keep.txt          the user's additions to the keep-list, one entry per line
  scripts/
    report/
      original.sql
      formatted.sql
      obfuscated.sql
      report.txt
```

- `settings.json` is written by the first `obfuscate` from its flags (`--dialect`, `--seed`, `--strings`, `--comments`). A later `obfuscate` that passes a different value is an error that names the stored value. Settings are never changed in place, because the mapping was built under them.
- `keep.txt` holds names, strings and numbers, one per line, compared case-insensitively. Blank lines are ignored.
- In milestone 1 a workspace holds one script. Several scripts sharing one mapping is milestone 2 and adds folders under `scripts/`; nothing else changes.
- Running `obfuscate` again on a changed script overwrites that script's four files. The mapping only grows (decision record 0004).
- `report.txt` is plain text in milestone 1 and lists the statements left unformatted, the renamed words that might be built-ins, and the unquoted names that were kept because they read as keywords. Milestone 3 adds the response side.
- `format` and `map` print to standard output. The only files any command writes are inside the workspace.

## Consequences

- The mapping file format is pinned by tests. Changing it later needs a migration, because workspaces outlive releases.
- A user who wants the original layout back does not get it: the formatted script is the baseline for every diff, and `original.sql` is kept only for reference.
- `obfuscate` is the one command that does two jobs in sequence. That is deliberate: a formatted script that was never obfuscated is a dead end, and a script obfuscated without formatting would make every later diff noisy.
