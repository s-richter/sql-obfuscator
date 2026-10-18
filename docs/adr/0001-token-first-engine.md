---
status: accepted
---
# The engine renames on the token stream, not the syntax tree

The engine replaces names and values by walking sqlglot's token stream and renaming every name that is not on the keep-list. sqlglot's parser is used only for pretty-printing and for classifying names in statements it parses cleanly. We chose this because 20-30% of the target scripts are T-SQL procedures, and the parser (tested on sqlglot 30.22.0) fails on them in three ways: hard errors (`GO`, `THROW`, `IF ... ELSE` around `UPDATE` or `INSERT`), opaque "Command" fallbacks whose contents would pass through unobfuscated (`TRY/CATCH`, cursors, triggers), and silent rewrites into invalid SQL (`IF @x IS NULL SET ...`, `IF ... ELSE` around `SELECT`, `OPEN cur`) that an idempotence check does not detect. These behaviours are pinned in `tests/test_sqlglot_assumptions.py`. The tokenizer copes with all of those constructs once its command mode is switched off (see Consequences).

## Considered Options

- **Syntax tree only** (parse, rename nodes, regenerate): the obvious use of sqlglot, rejected because unparsed regions leak or get corrupted.
- **Syntax tree with refusal** (reject scripts containing unparseable statements): safe, but would reject most procedures.

## Consequences

- sqlglot's tokenizer has a command mode: after `GO`, `FETCH`, `PRINT`, `SHOW`, `RENAME` (T-SQL) or `MSCK REPAIR` (Hive) it swallows the rest of the statement, up to the next semicolon, as a single string token. Left on, whole queries after `GO` turn into one placeholder, and with strings kept they would pass through unobfuscated. The engine must tokenize with command mode off and fail if a swallowed region ever appears.
- Evidence: a 60-line throwaway version of this approach, with command mode off, gave an exact round-trip, an identical token-type sequence and no leaked name on all 28 sample scripts of the earlier attempt (9,689 lines, 2,518 names, 976 values). With the current sqlglot parser, the nine procedural T-SQL samples do not parse.

- Mistakes fail towards over-obfuscation: an unknown built-in gets a fake name, which is confusing but reversible and never a leak. This holds only because a token's type never decides on its own that a word is structural; see decision record 0009.
- We maintain the keep-list ourselves; sqlglot's tokenizer reports `IF`, `TRY`, `THROW`, `OPEN`, `WHILE` as plain names and its function table lacks e.g. `STRING_SPLIT` and `SCOPE_IDENTITY`.
- Original layout survives obfuscation, so round-trips can be exact and comments can be swapped for placeholders and restored.
- Do not "simplify" the engine to a syntax-tree transform without re-running the procedural test scripts.
