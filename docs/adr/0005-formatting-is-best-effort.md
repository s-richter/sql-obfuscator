---
status: accepted
---
# Formatting is best-effort and limited to safe statement types

Only plain statements (`SELECT`, `INSERT`, `UPDATE`, `DELETE`, `MERGE`, `CREATE TABLE/VIEW/INDEX`) are pretty-printed with sqlglot; procedural code is left as written and listed in the report, and any statement for which sqlglot emits a warning is also left as written. sqlglot silently rewrites some procedural statements into invalid SQL, and comparing names and values before and after formatting does not detect it, so an allow-list of statement types is the only safe gate we found. Obfuscation never depends on formatting succeeding.

## Consequences

- A formatted script can be partly unformatted; that is expected, not a bug.
- Formatting queries inside procedure bodies is a planned milestone (split the body, format the plain statements inside). Writing our own formatter for procedural code is ruled out.
- Formatting changes more than whitespace (`INT` becomes `INTEGER`, `Total = SUM(x)` becomes `SUM(x) AS Total`, a `--` comment becomes a `/* */` comment at the end of its line); this is accepted.
- A script is cut into chunks at `GO` and at top-level semicolons. A chunk is formatted only if sqlglot parses it as exactly one statement of an allowed type without a warning. A chunk that holds several statements without semicolons therefore stays as written and is listed in the report.
