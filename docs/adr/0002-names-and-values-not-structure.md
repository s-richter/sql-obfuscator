---
status: accepted
---
# We protect names and values, not structure

The guarantee is that no name or protected value reaches the LLM. Statement structure, keywords, built-in functions, data types and query shape stay visible, because the LLM needs them to explain, review or edit the script. Someone who already knows the schema could recognise a script by its shape; we accept that and do not add decoy statements, reordering or padding.

## Consequences

- Numbers are kept by default because most are structural (`TOP 10`, `VARCHAR(100)`, `ORDER BY 1`); strings are replaced by default.
- Everything else shown to an LLM (the task text, user notes) is subject to the same guarantee and must pass through the mapping and the ban-list.
- Every obfuscation runs the round-trip, leak and ban-list checks itself. If one fails, no obfuscated script is written and there is deliberately no flag to override that.
