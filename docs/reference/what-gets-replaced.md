# What gets replaced and what is kept

This page states exactly what an obfuscated script hides and what it still shows.
Read it before relying on the tool for a script that contains sensitive numbers.

The promise: **no name and no protected value reaches the LLM.** The structure of the
script stays visible on purpose, because the LLM needs it to do its job.

## At a glance

| In the script | Default | Can be changed with |
|---|---|---|
| Names (tables, columns, variables, ...) | Replaced | `keep.txt` |
| Strings | Replaced | `--strings keep`, `keep.txt` |
| Numbers | **Kept** | `--numbers obfuscate` (from milestone 2) |
| Comments | Replaced by a marker, restored later | `--comments strip` or `keep` |
| Keywords, built-in functions, data types | Kept | - |
| Structure and layout | Kept | - |

## Names

Every name that is not on the keep-list is replaced by a fake name made of an adjective
and an animal, for example `frozen_lion`.

- **What counts as a name:** databases, schemas, tables, views, columns, aliases, CTEs,
  temporary tables, variables, procedures, functions, indexes and constraints.
- **Qualified names** are replaced part by part. `SalesDB.dbo.Customers` becomes something
  like `quiet_heron.dbo.frozen_lion`, so `Customers` and `dbo.Customers` stay recognisably
  the same table.
- **One name, one fake name.** A table and a column that are both called `Status` get the
  same fake name. `Customers` and `CUSTOMERS` are the same name; the fake name follows the
  casing (`Frozen_Lion`, `FROZEN_LION`).
- **Sigils and quoting stay.** `@CustomerId` becomes `@Gentle_Otter`, `#Recent` becomes
  `#Calm_Lynx`, `[Customer Name]` becomes `[Brisk_Moth]`.
- **Kept by default:** SQL keywords, built-in functions, data types, hints, and the system
  names `dbo`, `sys` and `INFORMATION_SCHEMA`. You can add harmless names of your own to
  `keep.txt` in the workspace.
- **Unknown words are replaced.** If the tool does not recognise a built-in function, it
  gives it a fake name and lists it in the report. That is confusing for the LLM but never
  a leak; add the word to `keep.txt` to fix it.

## Strings

Every string is replaced by a numbered placeholder such as `'text_017'`. The same string
always gets the same placeholder. The `N` prefix and the quote style are kept.

Kept as they are, because they matter for the logic and carry no secret:

- the empty string `''`
- strings made only of punctuation or whitespace, such as `','` or `' - '`
- the standard Hive SerDe and file-format class names
- anything you add to `keep.txt`

Things to know:

- The **whole** string is replaced. `LIKE 'ACME%'` becomes `LIKE 'text_018'`; the wildcard
  is hidden together with the text.
- Dates written as strings (`'2024-01-01'`) are replaced like any other string.
- SQL that is built inside strings (dynamic SQL) is replaced as a whole. It cannot leak,
  but the LLM cannot read it either.
- Short flags such as `'Y'` and `'N'` are replaced. Add them to `keep.txt` if the LLM
  should see them.

## Numbers

**By default, every number in the script is kept and is visible to the LLM.** Most numbers
are part of the logic (`TOP 10`, `VARCHAR(100)`, `ORDER BY 1`, `DATEADD(day, -30, ...)`),
and hiding them would make the script hard to reason about.

If your scripts contain sensitive numbers such as account numbers, thresholds or prices,
switch number obfuscation on with `--numbers obfuscate` (available from milestone 2).

### The rule when number obfuscation is on

> **Proposed, not final.** This rule has been agreed but not yet tried on scripts.
> Milestone 2 will test it and may adjust it; this page changes together with the rule.

A number is **replaced** if it

- has four or more digits, or
- has a decimal point.

A number is **kept** if it

- is a whole number with one to three digits, or
- is a size inside a data type, whatever its length.

A replaced number becomes a **different number of the same shape**: the same count of
digits before and after the decimal point. The same number always gets the same
replacement, and the pair is stored in the mapping so it can be restored exactly.

### Examples

| In the script | With `--numbers obfuscate` | Why |
|---|---|---|
| `WHERE AccountId = 4711283` | `WHERE frozen_lion = 8302516` | Seven digits: replaced. |
| `WHERE Total > 1000.50` | `WHERE calm_otter > 7316.84` | Decimal point: replaced. |
| `WHERE Year = 2024` | `WHERE shy_wolf = 6153` | Four digits: replaced. |
| `SET @Rate = 0.5` | `SET @Brisk_Moth = 0.3` | Decimal point: replaced. |
| `WHERE Status = 3` | `WHERE vivid_crane = 3` | One digit: kept. |
| `WHERE Limit = 999` | `WHERE keen_gecko = 999` | Three digits: kept. |
| `TOP 10`, `ORDER BY 1` | unchanged | One or two digits: kept. |
| `DATEADD(day, -30, ...)` | unchanged | Two digits: kept. The minus sign is not part of the number. |
| `CONVERT(VARCHAR(8), d, 112)` | unchanged | Type size and a three-digit style code: kept. |
| `VARCHAR(8000)`, `DECIMAL(18, 2)` | unchanged | Sizes inside a data type: always kept. |
| `TOP 1000` | `TOP 4821` | Four digits: replaced, although it is a row limit. |
| `Amount * 1.0` | `tidy_seal * 7.3` | Decimal point: replaced, although it only forces decimal arithmetic. |

### What this means in practice

- **The rule looks at how a number is written, not at what it is used for.** It cannot
  tell a threshold from a row limit. The last two rows of the table show the cost: some
  harmless numbers are replaced, and the LLM then sees a different number in their place.
  The round-trip is still exact.
- **Numbers below 1000 are never protected.** If a small whole number is sensitive (a
  branch code, a department number), this switch does not hide it. Put it on the ban-list
  so the tool refuses to produce a script that contains it.
- **To keep a specific number readable**, add it to `keep.txt`, for example `1.0` or
  `100.0`.
- **An LLM may do arithmetic on a replaced number** or change it. A changed number is not
  in the mapping; it comes back unchanged and is listed in the response report.

### Not yet decided

These are settled when milestone 2 is built, and this page will be updated then:

- numbers in scientific notation (`1e6`)
- hexadecimal and binary values (`0x1F`)
- money values with a currency sign (`$100`)

## Comments

Comments often describe exactly what the names hide, so they never reach the LLM as
written. By default each comment is replaced by a marker such as `/* c12 */` and put back
when the response is deobfuscated. The LLM is told to leave the markers where they are; a
marker that goes missing is listed in the response report.

- `--comments strip` removes comments completely. They are then not restored.
- `--comments keep` leaves them in. The leak check and the ban-list still apply to them.

## What stays visible

An obfuscated script still shows:

- which statements it contains and in what order
- keywords, built-in functions, data types and hints
- how many tables, columns and variables there are and how they relate
- every number, unless number obfuscation is on (see above)

Someone who already knows your database could recognise a script by this shape. The tool
does not try to prevent that.

## The safety net

Every time a script is obfuscated, the tool checks that

1. deobfuscating the result gives back the formatted script exactly,
2. no name or protected value from the original is left in the result,
3. the result has the same structure as the formatted script: the same kinds of tokens in
   the same order, so nothing was added, dropped or merged, and
4. nothing on the ban-list appears in the result (from milestone 2).

If any check fails, no obfuscated script is written. There is no option to override this.

The task text you write for the LLM goes through the same replacement, and through the
leak and ban-list checks.
The tool cannot catch a sensitive word that appears in no script and is not on the
ban-list, so read the bundle preview before you send it.
