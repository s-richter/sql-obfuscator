---
status: accepted
---
# Formatting is verified token by token, keyword-shaped words are names unless proved otherwise, and a name has one spelling

A design review on 18 October 2026 found four holes in the decisions of milestone 0 and the milestone 1 defaults of 16 October. This record closes them with the smallest change to each affected record (0001, 0003, 0005 and 0008) and leaves everything else as decided. The review's own remedies, which added a refusal mode, a per-script restoration file and a fourth copy of every script, were not adopted; the considered options below say why.

## 1. A formatted statement must match the original token by token

sqlglot rewrites `CREATE TABLE t (c NTEXT)` into `CREATE TABLE t (c VARCHAR(MAX))` without a warning, and `NTEXT` and `TEXT` produce identical syntax trees. So the gate in record 0005 (an allowed statement type and no warning) is necessary but not sufficient, and comparing trees cannot close the gap. After sqlglot produces a candidate, the engine compares the source text of every token in the original chunk with the candidate's tokens. The complete list of permitted differences is:

- whitespace and line breaks between tokens;
- the letter case of keywords, built-in functions and data types;
- `INT` written as `INTEGER`, and `DECIMAL` as `NUMERIC`;
- `AS` inserted before an alias;
- a column in a subquery or CTE given an alias equal to its own name (`r.UserId AS UserId`);
- a `--` comment written as a `/* */` comment at the end of its line, provided every comment of the chunk survives in the same order.

Any other difference leaves the chunk as written and lists it in the report. The `Total = SUM(x)` rewrite that record 0005 accepted is not on the list: it reorders tokens and needs its own rule, which waits until a script needs it. Evidence from running this gate over the 35 T-SQL test scripts:

| Chunks of the T-SQL scripts | Count |
|---|---|
| Cut at `GO` and top-level semicolons | 615 |
| Plain statements that pass the record 0005 gate | 191 |
| Pass the token comparison with the list above | 189 |
| Rejected because a comment is lost or reordered | 2 |

The two rejections are correct: sqlglot drops or moves those comments.

## 2. A keyword-shaped word is a name unless a rule proves otherwise

sqlglot's tokenizer types `Date`, `Comment` and `Format` as keywords, but T-SQL does not reserve them, so they are legal unquoted column names and script 45 uses them that way. Record 0001 claimed every mistake over-obfuscates; keeping such a column because of its token type is the one mistake that under-obfuscates, and the leak check could not catch it because the word never entered the mapping. The rule is now: a token's type never decides on its own. Every word token is a name unless

- its text is a reserved word of T-SQL (the engine ships Microsoft's documented list),
- it is a known built-in function and is followed by `(`,
- it is a type word in a type position: after `AS` inside `CAST`, `CONVERT`, `TRY_CAST` or `TRY_CONVERT`; after a name in a `DECLARE`, a column definition, a parameter list or `RETURNS`; after `ADD` or `ALTER COLUMN name` in `ALTER TABLE`,
- or it is on the keep-list (system objects and the user's `keep.txt`).

Where no rule applies, the word is renamed and listed in the report as possibly structural. That can hide a harmless type word from the LLM, which is confusing but reversible and never a leak, so record 0001's safety property holds again. The structure check compares token types with every renamed word counted as a name token, because `Date` arrives as a type token and leaves as a name token.

## 3. A name has one spelling within a workspace

Record 0003 makes `CustomerId` and `customerId` one name, and the 16 October default let the fake name follow each occurrence's casing. Script 31 shows why that cannot round-trip: both spellings give `Gentle_Otter`, so the mapping cannot say which spelling an occurrence had. Now the formatted script writes every occurrence of a name in the spelling the workspace first saw, keeping each occurrence's quoting and sigil. This is a token-level rewrite applied to the whole script, including chunks sqlglot did not format. The fake name's casing rule (all upper, all lower, otherwise capitalised) applies to that one spelling. The round-trip is byte-exact against the formatted script and the mapping alone restores it.

## 4. Stripped comments are removed from the formatted script

With `--comments strip`, the round-trip cannot give back a formatted script that still contains the comments. So in that mode the comments are removed from the formatted script itself, with a single space left where two tokens would otherwise touch. `original.sql` in the workspace keeps them. Record 0008's pipeline order is unchanged: format, then apply the comment setting, then replace names and values.

## Considered Options

- **Refuse a script when a word's role cannot be proved** (the review's proposal): safe, but record 0001 already rejected refusal because it would reject most procedures, and the proposal gave no criterion for "unresolved". Renaming when in doubt is equally safe and keeps procedures usable.
- **Document keyword-shaped names as a known limit** (the 16 October default): withdrawn. A column name shown to the LLM is exactly what the tool promises not to do.
- **Per-occurrence restoration metadata** (the review's proposal for casing): a second secret file per script with digests and spans, and two kinds of deobfuscation. Rejected because formatting already normalises keyword casing, and normalising name casing the same way solves the problem with no new state.
- **Case-insensitive round-trip**: rejected; every later diff against the formatted script would show casing noise.
- **A separate baseline file for the strip mode**: rejected as a fourth copy of every script for one setting.
- **Comparing syntax trees instead of tokens**: rejected because `NTEXT` and `TEXT` have equal trees.

## Consequences

- Formatting needs its own test: the formatted T-SQL scripts must pass the token comparison, and `tests/test_sqlglot_assumptions.py` pins the rewrites on the permitted list so a sqlglot upgrade that adds one is noticed.
- The engine ships a T-SQL reserved-word list next to the adjective and animal lists. It is part of the keep-list.
- Name casing in the formatted script can differ from the original. Databases that distinguish names only by case are unsupported, as record 0003 already assumes.
- A type word renamed by mistake shows the LLM a fake name where a type belongs. The report lists it, and `keep.txt` fixes it for that workspace.
- `docs/reference/what-gets-replaced.md` gains a Formatting section and loses the known-limit bullet. Records 0001, 0003, 0005 and 0008 each gain one sentence pointing here; their text is otherwise unchanged.
