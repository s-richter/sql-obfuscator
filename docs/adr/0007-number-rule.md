---
status: proposed
---
# Numbers are replaced by size, not by position

Numbers are kept by default. When number obfuscation is switched on, a number is replaced if it has four or more digits or a decimal point, and kept otherwise; sizes inside a data type (`VARCHAR(8000)`, `DECIMAL(18, 2)`) are always kept. The replacement is a different number of the same shape, recorded in the mapping. We chose a rule based on how the number is written because the engine works on tokens (ADR 0001) and cannot reliably tell a threshold from a row limit in procedural code; a positional rule would be wrong in exactly the scripts that matter most.

This record is proposed, not accepted. The rule was agreed in discussion but has not run against a script yet. It becomes accepted when milestone 2 has run it against `tests/scripts/tsql/37_tsql_literals.sql` and `tests/scripts/hive/55_hive_literals_and_comments.sql` and has settled the open cases (money values, scientific notation, hexadecimal values). Until then the rule may still change.

## Consequences

- The rule is a heuristic and both of its edges are visible to users: `999` is kept while `1000` is replaced; `TOP 1000` and `x * 1.0` are replaced although they are structural. The exact behaviour, with examples, is documented for users in `docs/reference/what-gets-replaced.md`, and that page must change together with the rule.
- Sensitive numbers below 1000 are not protected by this switch; the ban-list is the tool for those.
- Ships in milestone 2, not milestone 1.
