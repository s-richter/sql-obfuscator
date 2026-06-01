# Python Workflow API

The workflow API exposes the same core operations as the CLI without reading files, printing
output, or depending on HTTP concepts.

Use it when integrating SQL obfuscation into another Python application.

## Main Imports

```python
from sql_obfuscator.workflow import (
    ObfuscationOptions,
    TranslationOptions,
    analyze_deobfuscation,
    apply_statement_replacements,
    prepare_workspace,
    require_safe_deobfuscation,
    translate_document,
    validate_deobfuscation,
    verify_roundtrip,
)
from sql_obfuscator.workspace import (
    load_workspace_snapshot,
    save_workspace_snapshot,
)
```

## Prepare A Workspace In Memory

```python
from sql_obfuscator.workflow import ObfuscationOptions, prepare_workspace

prepared = prepare_workspace(
    "SELECT CustomerId FROM Customers;",
    input_name="script.sql",
    options=ObfuscationOptions(
        dialect="tsql",
        seed=42,
    ),
)

print(prepared.snapshot.obfuscated_sql)
```

`prepare_workspace()` returns:

- original SQL and input name
- generated LLM instructions
- a `WorkspaceSnapshot`
- external-sharing safety findings

## Preview Generated LLM Instructions

```python
from sql_obfuscator.llm_instructions import build_default_llm_instructions

instructions = build_default_llm_instructions(
    input_name="script.sql",
    dialect="tsql",
    statement_anchors=prepared.snapshot.context_payload["statement_anchors"],
)
print(instructions)
```

Instruction rendering is host-neutral. A desktop or web host can preview the generated
Markdown without importing local workspace persistence. `sql_obfuscator.workspace` retains
its existing `build_default_llm_instructions()` entry point as a compatibility delegator.

The snapshot contains:

- obfuscated SQL
- identifier mapping payload
- context payload
- optional reversible-redaction payload
- privacy summary
- LLM workflow report

## Prepare SQL For External Sharing

```python
from sql_obfuscator.workflow import LlmSafetyError, ObfuscationOptions, prepare_workspace

try:
    prepared = prepare_workspace(
        sql_text,
        input_name="script.sql",
        options=ObfuscationOptions(
            dialect="tsql",
            redaction_mode="irreversible",
            redact_literals=True,
            strip_comments=True,
            llm_safe=True,
        ),
    )
except LlmSafetyError as exc:
    prepared = exc.prepared
    for blocker in exc.safety.blockers:
        print(blocker)
```

`llm_safe=True` rejects known higher-risk visible content. It does not enable redaction
automatically. See [Sharing SQL With an External LLM](../guides/llm-sharing.md).

## Save And Load A Workspace

```python
from pathlib import Path

from sql_obfuscator.workspace import load_workspace_snapshot, save_workspace_snapshot

save_workspace_snapshot(
    workspace_path=Path("script.obf"),
    input_path=Path("script.sql"),
    original_sql=prepared.original_sql,
    snapshot=prepared.snapshot,
    instructions_text=prepared.instructions_text,
)

snapshot = load_workspace_snapshot(Path("script.obf"))
```

The filesystem helpers preserve the workspace layout and integrity checks described in
[Workspaces and Reports](workspaces-and-reports.md).

For a desktop host that persists local workspace folders, use the explicit local adapter:

```python
from pathlib import Path

from sql_obfuscator.local_workspace_store import LocalWorkspaceStore

store = LocalWorkspaceStore()
store.save_workspace_snapshot(
    workspace_path=Path("script.obf"),
    input_path=Path("script.sql"),
    original_sql=prepared.original_sql,
    snapshot=prepared.snapshot,
    instructions_text=prepared.instructions_text,
)
snapshot = store.load_workspace_snapshot(Path("script.obf"))
```

The functions in `sql_obfuscator.workspace` remain available as compatibility delegators
to `LocalWorkspaceStore`. A future web host can provide tenant-scoped persistence without
changing the host-neutral workflow operations.

## Inspect A Local Workspace

```python
from pathlib import Path

from sql_obfuscator.local_workspace_store import LocalWorkspaceStore

inspection = LocalWorkspaceStore().inspect_workspace(Path("script.obf"))
print(inspection.dialect)
print(inspection.integrity_algorithm)
print(inspection.artifacts["reports/privacy_summary.json"])
```

`inspect_workspace()` validates integrity and returns structured settings, counts, privacy
flags, and artifact availability. The CLI renders this result as text. A desktop host can
render an artifact tree, and a web host can expose the same facts on a workspace page.

## Apply Structured LLM Edits

```python
from sql_obfuscator.workflow import apply_statement_replacements

anchor_sql = prepared.snapshot.context_payload["statement_anchors"][0]["obfuscated_sql"]
edits_payload = {
    "schema_version": 1,
    "format": "statement_replacements",
    "edits": [
        {
            "statement_id": "stmt_0001",
            # Edit the SQL while preserving generated identifiers from obfuscated.sql.
            "sql": anchor_sql,
        }
    ],
}

application = apply_statement_replacements(prepared.snapshot, edits_payload)
print(application.applied_obfuscated_sql)
```

The operation validates statement IDs and replacement SQL while preserving untouched
statements exactly.

## Analyze And Require Safe Restoration

```python
from sql_obfuscator.workflow import analyze_deobfuscation, require_safe_deobfuscation

result = analyze_deobfuscation(
    prepared.snapshot,
    application.applied_obfuscated_sql,
)

require_safe_deobfuscation(result)
print(result.deobfuscated_sql)
```

`analyze_deobfuscation()` returns restored SQL, a diagnostic report, safety findings, and an
updated LLM workflow report.

Workflow results also expose host-neutral `diagnostics` tuples. Each `WorkflowDiagnostic`
contains a stable `code`, `severity`, user-facing `message`, optional `recommendation`, and
optional statement or identifier context:

```python
for diagnostic in result.diagnostics:
    print(diagnostic.severity, diagnostic.code, diagnostic.message)
    if diagnostic.statement_anchor:
        print("statement:", diagnostic.statement_anchor)
```

Use these structured diagnostics for a desktop results panel or a web response. Keep the raw
report payload when a user needs the full audit artifact. Preparation diagnostics are available
as `prepared.safety.diagnostics`; restoration and translation diagnostics are available directly
on their workflow results.

`require_safe_deobfuscation()` raises when unresolved or low-confidence findings remain.
Override arguments exist for deliberate manual-review workflows:

```python
require_safe_deobfuscation(
    result,
    allow_unresolved=True,
    allow_low_confidence=True,
)
```

Use `validate_deobfuscation()` when the host needs the common analyze-then-enforce sequence:

```python
from sql_obfuscator.workflow import validate_deobfuscation

result = validate_deobfuscation(
    prepared.snapshot,
    application.applied_obfuscated_sql,
)
print(result.deobfuscated_sql)
```

## Verify A Roundtrip

```python
from sql_obfuscator.workflow import verify_roundtrip

result = verify_roundtrip(
    "SELECT CustomerId FROM Customers;",
    input_name="script.sql",
    options=ObfuscationOptions(seed=42),
)

print(result.normalized_exact_match)
```

Use `verify_roundtrip()` when checking whether a script can be obfuscated and restored
without an intervening edit.

## Translate A Document

```python
from sql_obfuscator.workflow import TranslationOptions, translate_document

result = translate_document(
    "SELECT [CustomerId] FROM [Customers];",
    options=TranslationOptions(
        source_dialect="tsql",
        target_dialect="hive",
        validate=True,
    ),
)

if result.succeeded:
    print(result.translation.output_sql)
else:
    print(result.translation.failures)
```

`translate_document()` returns the translation report together with the host-neutral
success decision used by the CLI. A GUI or web adapter can render the same structured
result without reconstructing command rules.

## Adapter Responsibilities

The workflow module owns SQL transformation, operation sequencing, and validation. A host
adapter owns:

- reading input
- choosing storage
- persisting artifacts
- rendering messages
- mapping failures to CLI exit codes, HTTP responses, or job status

The CLI is one adapter. A future web adapter should reuse the workflow operations while
adding tenant-scoped storage, opaque workspace IDs, request handling, and resource limits.

## Local Application Adapter

Use `LocalWorkspaceApplication` when a desktop host needs workflow operations plus local
workspace persistence:

```python
from pathlib import Path

from sql_obfuscator.local_application import LocalWorkspaceApplication
from sql_obfuscator.workflow import ObfuscationOptions

app = LocalWorkspaceApplication()
operation = app.prepare_and_save_workspace(
    sql_text,
    input_path=Path("script.sql"),
    options=ObfuscationOptions(llm_safe=True),
)

print(operation.workspace_path)
print(operation.written_artifact_paths)
for diagnostic in operation.diagnostics:
    print(diagnostic.severity, diagnostic.message)
```

The adapter composes the host-neutral workflow module with `LocalWorkspaceStore`. Its
structured results report workspace paths, written artifacts, and diagnostics without
printing output or choosing terminal exit codes. The CLI uses the same adapter and remains
responsible for argument parsing, stdin, terminal messages, sibling output files, and exit
codes.

## Related Documents

- [Sharing SQL With an External LLM](../guides/llm-sharing.md)
- [Workspaces and Reports](workspaces-and-reports.md)
- [Command Reference](cli.md)
