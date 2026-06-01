# Python Workflow API

The workflow API exposes the same core operations as the CLI without reading files, printing
output, or depending on HTTP concepts.

Use it when integrating SQL obfuscation into another Python application.

## Main Imports

```python
from sql_obfuscator.workflow import (
    ObfuscationOptions,
    analyze_deobfuscation,
    apply_statement_replacements,
    prepare_workspace,
    require_safe_deobfuscation,
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
automatically. See [Sharing SQL With an External LLM](LLM_SHARING.md).

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
[Workspaces and Reports](WORKSPACES.md).

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

`require_safe_deobfuscation()` raises when unresolved or low-confidence findings remain.
Override arguments exist for deliberate manual-review workflows:

```python
require_safe_deobfuscation(
    result,
    allow_unresolved=True,
    allow_low_confidence=True,
)
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

## Adapter Responsibilities

The workflow module owns SQL transformation and validation. A host adapter owns:

- reading input
- choosing storage
- persisting artifacts
- rendering messages
- mapping failures to CLI exit codes, HTTP responses, or job status

The CLI is one adapter. A future web adapter should reuse the workflow operations while
adding tenant-scoped storage, opaque workspace IDs, request handling, and resource limits.

## Related Documents

- [Sharing SQL With an External LLM](LLM_SHARING.md)
- [Workspaces and Reports](WORKSPACES.md)
- [Command Reference](COMMAND_REFERENCE.md)
