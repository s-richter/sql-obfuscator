# SQL Obfuscator

Get LLM help with SQL scripts whose names and values must not leave your organisation.
The tool replaces them reversibly, you share the obfuscated script, and the answer is
translated back into your real names.

```sql
-- original
SELECT c.CustomerName, o.Total
FROM SalesDB.dbo.Customers c
JOIN SalesDB.dbo.Orders o ON o.CustomerId = c.Id
WHERE c.Region = 'EMEA'

-- obfuscated
SELECT warm_seal.Gentle_Otter, tidy_mole.Calm_Lynx
FROM Quiet_Heron.dbo.Frozen_Lion warm_seal
JOIN Quiet_Heron.dbo.Brisk_Moth tidy_mole ON tidy_mole.Vivid_Crane = warm_seal.Shy_Wolf
WHERE warm_seal.Keen_Gecko = 'text_001'
```

Supported dialects: T-SQL first, then Hive.

## Status

Milestone 0 (foundation) is complete: the design is recorded, the test scripts and word
lists are in place, and the command line exists as a skeleton. The commands do not do
anything yet; milestone 1 implements them. See [docs/milestones.md](docs/milestones.md).

## The promise, and its limits

No name and no protected value reaches the LLM. Structure, keywords, built-in functions
and data types stay visible, and **numbers are kept by default**.
[What gets replaced and what is kept](docs/reference/what-gets-replaced.md) states the
rules exactly.

## Commands

| Command | Purpose |
|---|---|
| `sqlobf obfuscate` | Create or update a workspace from one or more scripts. |
| `sqlobf bundle` | Produce instructions, task and obfuscated script for an LLM. |
| `sqlobf deobfuscate` | Translate any text (SQL, Markdown, HTML) back using a workspace's mapping. |
| `sqlobf format` | Pretty-print a script without obfuscating it. |
| `sqlobf map` | Show, search or export the mapping. |

A workspace is a folder ending in `.obf`. It holds the mapping, which is as sensitive as
your original scripts, so a workspace ignores itself in git.

## Development

```bash
uv sync
uv run pytest
uv run ruff check
uv run ruff format --check
```

## Where things are

- [CONTEXT.md](CONTEXT.md): the project's vocabulary. Use these terms in code and docs.
- [docs/adr/](docs/adr/): why the design is the way it is. Read 0001 before touching the engine.
- [docs/reference/what-gets-replaced.md](docs/reference/what-gets-replaced.md): the user-facing rules.
- [docs/milestones.md](docs/milestones.md): the plan.
- [docs/history/](docs/history/): one self-contained HTML page per finished milestone: what was done, the evidence, and what we would do differently. Open the file in a browser.
- [tests/scripts/](tests/scripts/README.md): the SQL test scripts.
