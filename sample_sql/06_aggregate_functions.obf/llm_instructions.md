# LLM Instructions for Obfuscated SQL

You are optimizing an obfuscated SQL script. The output will be de-obfuscated afterward.

## Input Context
- Original input file: `06_aggregate_functions.sql`
- SQL dialect: `tsql`

## Requirements
1. Keep obfuscated identifiers unchanged whenever possible.
2. Do not invent new table/column names unless absolutely required.
3. Keep alias structure stable where possible.
4. Prefer structural/query-plan improvements over renaming.
5. Preserve SQL semantics unless explicitly asked to change behavior.

## If new identifiers are unavoidable
- Minimize the number of new identifiers.
- Keep new identifiers syntactically valid for the dialect.
- Clearly comment where and why new identifiers were introduced.
