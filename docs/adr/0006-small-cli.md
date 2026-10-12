---
status: accepted
---
# The CLI stays small: one way per job, independent flags, no safety switches

The earlier attempt at this tool was abandoned largely because its command line became hard to use: nine commands in two overlapping layers (`obfuscate`/`deobfuscate` next to `prepare-for-llm`/`restore-from-llm`), flags that required or excluded each other, safety that could be switched off (`--llm-safe`, `--expert-mode`), and output written to three places. This tool has five commands (`obfuscate`, `bundle`, `deobfuscate` for the loop; `format` and `map` as helpers) and follows four rules.

1. One way to do each job. No command wraps other commands.
2. No flag requires or forbids another flag.
3. Safety is never a flag. The checks always run and cannot be overridden.
4. Output goes to the workspace only. Settings are stored there on first use, so later commands need no flags.

## Consequences

- A proposed sixth command or a flag that depends on another flag needs a new decision record, not just a pull request.
- Deliberately not carried over from the earlier tool: dialect translation, irreversible redaction, the sensitive-columns policy, override flags, structured edit files, and a separate `verify`/`roundtrip` command (`obfuscate` always verifies).
