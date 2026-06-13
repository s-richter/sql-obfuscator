# SQL Obfuscator And LLM Use Cases

This document helps choose an appropriate workflow for an LLM-assisted SQL task.

The key question is not only what you want the LLM to do. It is also how much the SQL may
change before automatic restoration becomes unreliable.

## Choose A Workflow

| Workflow | Use it when | Typical next step |
|---|---|---|
| Read-only review | The LLM explains or reviews SQL without returning executable edits. | Share approved sanitized SQL and review the response. |
| Small restorable edit | The LLM changes one or more existing statements while preserving generated names and overall structure. | Use structured statement replacements, then validate and restore. |
| Manual-review rewrite | The LLM introduces substantial structural changes or new identifiers. | Review output manually; automatic restoration may be incomplete. |
| Local translation | You need structural T-SQL/Hive conversion. | Use `translate --validate`; test behavior on the target database. |

For external sharing, start with
[Sharing SQL With an External LLM](llm-sharing.md).

## Read-Only Review Tasks

These are the simplest external-LLM tasks because no edited SQL needs to be restored:

- summarize what a query does
- explain joins, filters, aggregations, window functions, or CTE dependencies
- identify likely correctness risks
- identify likely performance issues
- produce review questions for a human
- describe source-to-output data flow
- explain temp-table lifecycle
- summarize dialect-specific constructs

Recommended preparation:

```bash
python obfuscator.py obfuscate script.sql \
  --llm-safe \
  --redaction-mode irreversible \
  --redact-literals \
  --strip-comments
```

## Small Restorable Edits

These tasks often fit the recommended structured-edit workflow:

- adjust a predicate
- add or remove an existing projected column
- correct `NULL` handling
- fix a date boundary condition
- replace `UNION` with `UNION ALL`, or the reverse, after review
- remove an unnecessary `DISTINCT`
- make a local aggregation correction
- add a small validation predicate
- make a local syntax correction
- apply a narrowly scoped optimization

Ask the LLM to return statement replacements. Then run:

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

## Manual-Review Rewrites

These tasks can still benefit from an LLM, but they are poor fits for unattended automatic
restoration:

- introduce new tables, columns, views, or indexes
- split a large query into multiple statements
- reorganize a script into a new CTE hierarchy
- replace temp-table workflows with a different architecture
- rewrite joins broadly
- generate DDL migrations
- add new ETL stages
- convert procedural SQL into set-based SQL
- produce rollback or deployment scripts
- perform a large cross-dialect rewrite

This is an **expert mode** workflow. The LLM output requires explicit human review, and
restoration may report unknown, ambiguous, or low-confidence identifiers.

Use `deobfuscate --dry-run` before writing restored SQL. Treat override flags as deliberate
manual-review tools, not as a routine next step.

## Translation Tasks

Use the built-in translation command for structural T-SQL/Hive conversion:

```bash
python obfuscator.py translate \
  --input script.sql \
  --source-dialect tsql \
  --target-dialect hive \
  --validate
```

Appropriate tasks:

- identify unsupported syntax
- produce a first-pass dialect conversion
- compare emitted SQL between dialects
- translate smaller query fragments during migration work

Translation validation checks parseability, not identical behavior. Test translated SQL on
the target database.

## Prompt Guidance

For small restorable edits, tell the LLM:

1. Preserve generated identifiers exactly.
2. Preserve placeholder values exactly.
3. Keep aliases and statement structure stable.
4. Return only the requested statement replacements.
5. Avoid introducing new table or column names unless the task requires them.
6. State when a requested change requires a broader rewrite.

Generated `llm_instructions.md` contains the workspace-specific statement IDs and response
format.

## Security And Governance Tasks

LLMs can provide review suggestions for:

- likely SQL injection risks
- parameterization opportunities
- potentially sensitive-column access
- broad permissions patterns
- missing filtering controls
- audit logging ideas
- data-retention or anonymization questions

Treat these as review suggestions, not proof of security or compliance.

## Testing And Quality Tasks

LLMs can suggest:

- row-count reconciliation queries
- duplicate detection queries
- null-rate or uniqueness checks
- pre-deployment and post-deployment validation SQL
- regression-test ideas
- edge-case scenarios
- semantic-equivalence questions for a reviewer

Generated SQL still requires review and execution in an appropriate test environment.

## Related Documents

- [Sharing SQL With an External LLM](llm-sharing.md)
- [Command Tutorial](command-tutorial.md)
- [Command Reference](../reference/cli.md)
- [Troubleshooting](troubleshooting.md)
