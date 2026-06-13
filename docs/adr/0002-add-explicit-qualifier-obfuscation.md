# Add Explicit Qualifier Obfuscation

Qualifier obfuscation will be an opt-in transformation exposed as
`--obfuscate-qualifiers`, not an automatic side effect of `--llm-safe`. It covers schema
qualifiers and catalog/database qualifiers on supported table references, column
references, and qualified function calls; preserves common schemas such as `dbo`, `sys`,
`information_schema`, and Hive `default` by default; leaves function names themselves
unchanged; maps qualifiers globally by mapping kind plus normalized original value; and
restores them through the normal workspace/deobfuscation flow.

This keeps `--llm-safe` as a validation check, keeps redaction limited to comments and
literal values, and avoids mixing qualifier privacy with the harder separate problem of
function-name obfuscation.
