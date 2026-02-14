Note: this document contains only a small amount of the used prompts and the answers from GPT-5.3-Codex

# User

Given the fact that the obfuscated identifiers shouldn't collide with SQLs reserved words, by saving the original identifiers and the corresponding obfuscated identifiers, translating back to the original script should be easy, or am I missing something here?

## GPT-5.3-Codex

You’re mostly right, with a few important caveats.

If you persist a full mapping (`original -> obfuscated` and ideally `obfuscated -> original`), de-obfuscation is straightforward for identifiers. But exact round-trip back to the original _file_ is not guaranteed because:

1. Formatting/comments are normalized by `sqlglot`.
2. Identifier normalization is many-to-one (`UserId`, `[userid]`, `USERID` map together), so original casing/bracketing can be lost.
3. Aliases are now obfuscated too, so they must be included in the map.
4. Context matters for ambiguous names (`Id` used in multiple scopes); AST-based replacement is safer than plain string replace.

So: reversible at the identifier/AST level is practical, but byte-for-byte source restoration is not guaranteed unless you also store extra metadata (original token text, casing, brackets, formatting/comments).

# User

How much effort would it be to create a perfect mapping?

## GPT-5.3-Codex

For a truly “perfect” mapping (round-trip to the exact original file, including casing, brackets, whitespace, comments, and formatting), effort is high.

Rough estimate:

1. Identifier-only reversible mapping (semantic SQL round-trip): 0.5-1.5 days.
2. Strong round-trip with original casing/bracketing and alias scopes preserved: 2-4 days.
3. Byte-for-byte perfect source reconstruction: 1-3 weeks.

Why #3 is hard:

- Current pipeline reparses and regenerates SQL via `sqlglot`, which normalizes layout/comments.
- You’d need token-level capture and replay (or a custom lexer/token patching layer), not just AST transforms.
- You also need robust scope-aware mapping storage and deterministic de-obfuscation logic.

So if your goal is practical de-obfuscation of names, that’s relatively easy. If your goal is exact original file reproduction, that’s a much bigger project.

# User

Consider the following scenario: a user obfuscates an SQL script and then asks an LLM to optimize the obfuscated script. Would de-obfuscation of the resulting script in that case be reasonable?

## GPT-5.3-Codex

Yes, reasonable, but only with constraints.

It works well if:

1. The LLM keeps the same schema/identifier structure and mostly does query-shape rewrites.
2. You de-obfuscate with AST/context-aware mapping, not raw text replace.
3. You handle newly introduced identifiers explicitly (leave as-is or map via policy).

Main risks:

1. LLM may invent/drop/rename identifiers outside your map.
2. It may change scope/alias structure so mapped names become ambiguous.
3. It can introduce semantic changes; de-obfuscation won’t catch logic regressions.

Practical approach:

1. Save forward+reverse mapping.
2. Re-parse optimized SQL and de-obfuscate only mapped identifiers.
3. Emit a report:
   - mapped successfully
   - unknown new identifiers
   - removed mapped identifiers
4. Run validation tests (parse + optional execution checks).

So: reasonable and often useful, but treat it as “best-effort with guardrails,” not guaranteed perfect round-trip.

# User

Would informing the LLM that this is an obfuscated script and that it should take the following de-obfuscating into account improve the situation, if the LLM is a top-of-the-line LLM?

## GPT-5.3-Codex

Yes, materially.

Even with a top-tier LLM, explicit instructions help it avoid breaking reversibility.

Tell it:

1. Identifiers are obfuscated and must be preserved exactly unless necessary.
2. Do not invent new table/column names.
3. Keep alias structure stable where possible.
4. Prefer structural/query-plan improvements over renaming.
5. If new identifiers are unavoidable, mark them clearly.

You’ll still need post-checks (AST parse + mapping coverage report), but this prompt discipline significantly improves de-obfuscation success rates.
