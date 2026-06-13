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

## Use A Custom Identifier Vocabulary

Desktop and web hosts can load, validate, and preview edited identifier word lists before
using them for future operations:

```python
from pathlib import Path

from sql_obfuscator.names import IdentifierVocabulary
from sql_obfuscator.workflow import ObfuscationOptions, prepare_workspace

vocabulary = IdentifierVocabulary.load(
    adjectives_path=Path("identifier_adjectives.txt"),
    replacements_path=Path("identifier_replacements.txt"),
)

for diagnostic in vocabulary.validation_diagnostics():
    print(diagnostic.severity, diagnostic.message)

print(vocabulary.pool_size)
print(vocabulary.sample_names(count=5, seed=42))

prepared = prepare_workspace(
    "SELECT CustomerId FROM Customers;",
    input_name="script.sql",
    options=ObfuscationOptions(
        seed=42,
        identifier_vocabulary=vocabulary,
    ),
)
```

`IdentifierVocabulary` is immutable. Applying edited word lists creates a new vocabulary
for future operations. Existing providers and in-progress operations keep their original
snapshot. This avoids process-wide mutation when multiple desktop tabs or web requests use
different vocabularies.

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
            obfuscate_qualifiers=True,
        ),
    )
except LlmSafetyError as exc:
    prepared = exc.prepared
    for blocker in exc.safety.blockers:
        print(blocker)
```

`obfuscate_qualifiers=True` obfuscates custom schema qualifiers and catalog/database
qualifiers on table and column references. `llm_safe=True` rejects known higher-risk visible
content. It does not enable redaction or qualifier obfuscation automatically. See
[Sharing SQL With an External LLM](../guides/llm-sharing.md).

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
to `LocalWorkspaceStore`. New local persistence behavior should use
`LocalWorkspaceStore` or `LocalWorkspaceApplication`, not expand the compatibility surface.
A future web host can provide tenant-scoped persistence without changing the host-neutral
workflow operations.

## Run Local Workflow Operations

```python
from pathlib import Path

from sql_obfuscator.local_application import LocalWorkspaceApplication
from sql_obfuscator.workflow import ObfuscationOptions, TranslationOptions

app = LocalWorkspaceApplication()
prepared = app.prepare_and_save_workspace(
    sql_text,
    input_path=Path("script.sql"),
    options=ObfuscationOptions(seed=42),
)
print(prepared.summary.workspace_path)
print(prepared.summary.written_artifact_paths)

translated = app.translate_and_save_artifacts(
    sql_text,
    options=TranslationOptions(source_dialect="tsql", target_dialect="hive"),
    workspace_path=prepared.summary.workspace_path,
    persist_translated_sql=True,
)
print(translated.summary.translation.target_dialect)
print(translated.summary.translated_sql_persisted)
```

Local application methods return workflow results plus a `summary` object with structured
operation facts such as workspace path, output path, written artifacts, persistence status,
and typed workflow counts. CLI handlers render those summaries as text; desktop and web
hosts can render the same facts without reading report dictionaries.

## Inspect A Local Workspace

```python
from pathlib import Path

from sql_obfuscator.local_workspace_store import LocalWorkspaceStore

inspection = LocalWorkspaceStore().inspect_workspace(Path("script.obf"))
print(inspection.dialect)
print(inspection.integrity_algorithm)
print(inspection.artifacts["reports/privacy_summary.json"])

for artifact in inspection.artifact_statuses:
    print(artifact.relative_path, artifact.kind, artifact.available)
```

`inspect_workspace()` validates integrity and returns structured settings, counts, privacy
flags, and an ordered artifact inventory with media type, availability, read-only status,
and integrity protection metadata. `inspection.artifacts` remains a path-to-availability
shortcut for compatibility. The CLI renders this result as text. A desktop host can render
an artifact tree, and a web host can expose the same facts on a workspace page.

## Browse Local Workspace Artifacts

```python
from pathlib import Path

from sql_obfuscator.local_application import LocalWorkspaceApplication

app = LocalWorkspaceApplication()
workspace = app.open_workspace(Path("script.obf"))

for artifact in workspace.artifacts:
    print(artifact.relative_path, artifact.kind, artifact.available)

content = app.load_workspace_artifact(Path("script.obf"), "obfuscated.sql")
print(content.text)
```

`open_workspace()` validates integrity and returns an ordered artifact tree. Each artifact
describes its kind, media type, availability, read-only status, and whether workspace
integrity metadata protects it. `load_workspace_artifact()` reads only cataloged workspace
paths, rejects traversal, escaping links, and unknown paths, and validates integrity before
loading content.

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
as `prepared.diagnostics`; restoration and translation diagnostics are available directly on
their workflow results. Parser fallback notices from `sqlglot` use the
`sqlglot.fallback_parse` diagnostic code, so hosts can render the same warning facts as the
CLI without capturing terminal logs.

## Present Application Errors

Workflow operations continue to raise typed exceptions. Host adapters can map those failures
to stable user-facing metadata without duplicating error rules:

```python
from sql_obfuscator.application_errors import present_application_error

try:
    prepared = prepare_workspace(
        sql_text,
        input_name="script.sql",
        options=ObfuscationOptions(llm_safe=True),
    )
except Exception as exc:
    presentation = present_application_error(exc)
    print(presentation.code)
    print(presentation.title)
    print(presentation.message)
    print(presentation.recommendation)
    print(presentation.report_paths)
```

An `ApplicationErrorPresentation` contains a stable code, title, message, severity,
recommended recovery action, and relevant report paths. Desktop hosts can render dialogs,
web adapters can serialize the fields, and the CLI renders the message to `stderr`.
Unexpected exceptions receive a conservative generic message so internal details are not
exposed to users.

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
