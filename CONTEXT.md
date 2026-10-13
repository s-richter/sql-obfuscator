# SQL Obfuscator

Lets people get LLM help with SQL scripts whose names and values must not leave the organisation, by replacing them reversibly before the script is shared.

## Language

### Scripts

**Original script**:
A SQL script exactly as the user supplied it, including poor formatting, comments and errors.
_Avoid_: Input script, source script

**Formatted script**:
The original script after pretty-printing, with nothing renamed yet.
_Avoid_: Input script, normalized script, prettified script

**Obfuscated script**:
A formatted script in which every name and protected value has been replaced via the mapping; the only kind of script that may be shown to an LLM.
_Avoid_: Masked script, anonymized script

**Deobfuscated script**:
An obfuscated script with the mapping applied in reverse; expected to equal the formatted script.
_Avoid_: Restored script, decoded script

**Response**:
Whatever an LLM returns after being given an obfuscated script and a task: an edited script, prose, a diagram, or a mix.
_Avoid_: Answer, output, result

**Deobfuscated response**:
A response with the mapping applied in reverse, so the user reads it in their real names.

### Obfuscation

**Engine**:
The component that turns a formatted script into an obfuscated one and back.
_Avoid_: Parser (reserved for sqlglot's parser), obfuscator, transformer

**Name**:
Any user-chosen identifier part in a script: database, schema, table, view, column, alias, CTE, temporary table, variable, procedure, function, index or constraint. Names are compared case-insensitively and share one namespace regardless of kind.
_Avoid_: Identifier (when a single part is meant), object name

**Fake name**:
The adjective-plus-animal replacement for a name, such as `frozen_lion`.
_Avoid_: Alias (means a SQL alias here), pseudonym, token

**Placeholder**:
The opaque replacement for a protected value (a string literal, a number when enabled) or for a comment.
_Avoid_: Fake value, dummy

**Mapping**:
The complete two-way record of which name or value was replaced by which fake name or placeholder. It is as sensitive as the original scripts.
_Avoid_: Dictionary, lookup, translation table

**Keep-list**:
The words the engine never replaces: SQL keywords, built-in functions, data types and system objects, plus anything the user adds.
_Avoid_: Allowlist, whitelist, ignore list

**Ban-list**:
User-supplied strings and values that must never appear as a name or value in an obfuscated script.
_Avoid_: Blocklist, blacklist, deny list

### Working with an LLM

**Workspace**:
A folder ending in `.obf` that holds one mapping, the keep-list and ban-list, and every script obfuscated with that mapping together with its reports and responses. A single script and a set of related scripts are both workspaces.
_Avoid_: Project, session, repository

**Task**:
What the user asks the LLM to do with an obfuscated script: explain it, review it or change it.
_Avoid_: Prompt, question, request

**Bundle**:
Everything handed to an LLM for one task: the instructions, the task and the obfuscated script.
_Avoid_: Prompt, payload, package

**Report**:
The record of one obfuscation run: settings used, statements left unformatted, words renamed that might be built-ins, and check results.
_Avoid_: Log, notes, summary

### Assurance

**Guarantee**:
What obfuscation promises: no name or protected value reaches the LLM. Script structure, keywords, built-in functions and data types remain visible.

**Leak**:
Any name or protected value from an original script that is present in something shown to an LLM, including the task text.

**Round-trip**:
Obfuscating a formatted script and immediately deobfuscating it; it passes when the result equals the formatted script.

**Structure check**:
The comparison that passes when an obfuscated script has the same sequence of token types as its formatted script, showing that only names and values changed.
_Avoid_: Shape check, token check
