# SQL Obfuscator

SQL Obfuscator prepares SQL for local review, external LLM review, restoration after edits,
and dialect translation.

## Language

**Qualifier obfuscation**:
Replacing schema qualifiers and catalog/database qualifiers with generated names while
keeping enough mapping information to restore them later.
_Avoid_: Schema renaming, qualifier redaction

**Schema qualifier**:
The namespace immediately above an object name, such as `sales` in `sales.Orders` or
`sales` in `CustomerDW.sales.Orders`.
_Avoid_: Schema prefix

**Catalog qualifier**:
The upper namespace above a schema qualifier, such as `CustomerDW` in
`CustomerDW.sales.Orders`. User documentation may call this a catalog/database qualifier.
_Avoid_: Database qualifier as an internal mapping kind
