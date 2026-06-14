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

**Workflow command**:
A CLI command that represents a common user goal by coordinating one or more lower-level
operations or recommended defaults.
_Avoid_: Compound command, shortcut command

**Preparation workflow**:
The workflow that creates SQL and instructions suitable for sharing with an external LLM
while keeping local restoration metadata in a workspace.
_Avoid_: LLM-safe command

**Restoration workflow**:
The workflow that takes an LLM response for obfuscated SQL and restores original names
using the local workspace.
_Avoid_: De-obfuscation shortcut

**Reversible redaction**:
Redaction that replaces literal values with placeholders and keeps enough local workspace
metadata to restore the original values later.
_Avoid_: Safe redaction

**Irreversible redaction**:
Redaction that replaces literal values without keeping local workspace metadata that can
restore the original values later.
_Avoid_: One-way mode

**Fail-closed validation**:
Validation behavior that stops a workflow from producing approved sharing output when known
higher-risk content or incomplete checks remain.
_Avoid_: Safety mode

**Expert mode**:
A deliberate workflow path where the user accepts manual review responsibility for output
that automatic validation cannot approve.
_Avoid_: Unsafe mode

**Bounded edit**:
An LLM-assisted change that replaces specific known statements while leaving unrelated
statements untouched.
_Avoid_: Full rewrite
