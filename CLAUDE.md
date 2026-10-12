# Working in this repo

- Use the vocabulary in `CONTEXT.md` in code, tests and docs. "Input script" and "parser" (for our own code) are wrong words here.
- Read `docs/adr/0001-token-first-engine.md` before touching the engine. All tokenizing goes through `sql_obfuscator.tokens.tokenize`; never call `sqlglot.tokenize` directly, because sqlglot's command mode swallows text.
- The CLI has five commands and independent flags (`docs/adr/0006-small-cli.md`). Adding a command, or a flag that depends on another flag, needs a new decision record first.
- Safety checks are never optional and have no override.
- `docs/reference/what-gets-replaced.md` is the user-facing statement of the rules. Change it in the same commit as any rule it describes.
- Every new SQL test script gets a row in `tests/scripts/README.md`. Test scripts are compared byte for byte.
- A workspace (`*.obf/`) holds the mapping and original scripts. Never commit one.
- `tests/test_sqlglot_assumptions.py` pins sqlglot behaviour the design relies on. If it fails after an upgrade, reread the decision record named in the failing test.

```bash
uv sync
uv run pytest
uv run ruff check && uv run ruff format --check
```
