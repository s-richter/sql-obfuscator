# Milestones

Each milestone ends with its tests passing and a short validation note from a user who ran
it on real scripts. Only pass or fail counts and the failing construct are reported back,
never a script.

| # | Milestone | Contents | Status |
|---|---|---|---|
| 0 | Foundation | Repo, CI, glossary and decision records, word lists, test scripts. | Done |
| 1 | Core CLI, T-SQL | `format`, `obfuscate`, `deobfuscate`, `map`; workspace with one script; keep-list; report; round-trip, leak and structure checks; deobfuscating SQL and plain text. | Next |
| 2 | Hive and lists | Hive dialect, ban-list, number obfuscation, several scripts sharing one workspace. | Planned |
| 3 | LLM loop | `bundle`, task mapping, response handling and response reports; deobfuscating Markdown (including escaped underscores such as `frozen\_lion`), HTML and Mermaid. | Planned |
| 4 | Procedure formatting | Format the queries inside procedure bodies. | Planned |
| 5 | Web UI | FastAPI backend and React + Vite frontend, running locally. | Planned |
| 6 | LLM connection | Direct, provider-agnostic API calls; user notes on tables and columns; diagrams. | Planned |
| 7 | Team use | Central server, multi-user, `sync` and auto-update from changed files. | Planned |
| - | Local analysis | "Which objects use this table?" and "do we have similar code elsewhere?" | Parked |

## Decided later, on purpose

- Which LLM providers to support: milestone 6.
- Web UI details: milestone 5.
- The number rule (decision record 0007) is proposed until milestone 2 has tested it on the
  literals scripts. Scientific-notation, hexadecimal and money values are settled then too.
- Multi-user and auto-update details: milestone 7. Originals come from files only, never
  from a live database; multi-user means a central server holding workspaces.
- Formatting the `Total = SUM(x)` alias form: not permitted until a script needs it
  (decision record 0009). Such statements stay as written.

## Checks every obfuscation must pass

1. **Round-trip:** deobfuscating the obfuscated script gives the formatted script exactly.
2. **Leak:** no name or protected value from the mapping is left in the obfuscated script.
3. **Structure:** the obfuscated script has the same sequence of token types as the
   formatted script, counting every renamed word as a name token.
4. **Ban-list** (from milestone 2): nothing on the ban-list appears in the obfuscated script.

Tests additionally check that the same seed gives the same output.
