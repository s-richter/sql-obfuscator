# Round-Trip Obfuscation/De-Obfuscation Plan

## Goal
Enable a safe workflow where a user:
1. obfuscates a SQL script,
2. sends the obfuscated script to an LLM (properly instructed),
3. receives a changed obfuscated script,
4. de-obfuscates it back using stored metadata and mappings.

The implementation target is strong round-trip behavior for identifiers, including original casing/bracketing and alias scopes.

## Short answer: folder-per-script approach
Yes, this approach makes sense and should be the default.

Why:
- Keeps all artifacts (original, obfuscated, mapping, metadata, logs) together.
- Enables deterministic and auditable de-obfuscation runs.
- Reduces user mistakes when selecting mismatched files/mappings.
- Supports iterative LLM cycles (`v1`, `v2`, etc.) in one place.

## Proposed Artifact Folder Model
For input `C:\path\query.sql`, create (or reuse) a working folder, e.g.:

```text
query.obf/
|-- original.sql
|-- obfuscated.sql
|-- mapping.json
|-- context.json
|-- llm_instructions.md
|-- llm_response_obfuscated.sql            # user-provided edited obfuscated script
|-- deobfuscated.sql
|-- reports/
|   |-- deobfuscation_report.json
|   `-- coverage_report.txt
`-- logs/
    `-- operations.log
```

## Mapping Requirements (Strong Round-Trip)
Mapping cannot only be `normalized_name -> obfuscated_name`. It must capture lexical and scope details.

### Mapping record fields (minimum)
- `kind`: table | column | cte | alias | column_alias | column_def | insert_column
- `scope_id`: stable scope identity (statement index + AST path hash)
- `normalized_original`: lowercase canonical identifier used for matching
- `original_lexeme`: exact token text from source (`UserId`, `[UserId]`, etc.)
- `original_unbracketed`: lexeme without outer brackets (if any)
- `original_was_bracketed`: bool
- `original_case_pattern`: exact original token for restoration
- `temp_prefix`: `""` | `#` | `##`
- `obfuscated_lexeme`: emitted obfuscated identifier token
- `dialect`: e.g. `tsql`
- `statement_index` and `batch_index`

### Additional context for alias scope safety
- parent construct type (`SELECT`, `JOIN`, `UPDATE`, `CTE`, etc.)
- alias-role (`table_alias`, `projection_alias`, `cte_alias`, etc.)
- qualifier linkage where relevant (for `a.col` relationship)

## CLI Design (End-State)
Introduce explicit commands instead of overloading one command.

### 1) Obfuscate into workspace
`obfuscator.py obfuscate <input.sql> [--workspace <dir>] [--seed N] [--dialect tsql] [--pretty|--no-pretty]`

Behavior:
- Create workspace folder.
- Save `original.sql`, `obfuscated.sql`, `mapping.json`, `context.json`, `llm_instructions.md`.
- Print obfuscated SQL and workspace path.

### 2) De-obfuscate edited obfuscated script
`obfuscator.py deobfuscate --workspace <folder> --input <edited_obfuscated.sql> [--out deobfuscated.sql]`

Behavior:
- Load mapping/context.
- AST-parse edited obfuscated script.
- Reverse-map identifiers by kind + scope-aware matching.
- Restore original casing/bracketing using stored lexical data.
- Emit de-obfuscated SQL and report unknown/new identifiers.

### 3) Verify round-trip immediately (test mode)
`obfuscator.py roundtrip <input.sql> [--workspace <dir>] [--seed N] [--diff-report]`

Behavior:
- Obfuscate.
- Immediately de-obfuscate generated `obfuscated.sql`.
- Save `deobfuscated.sql` and report.
- Exit non-zero if mapping coverage or parse checks fail.

### 4) (Optional but useful) Explain workspace status
`obfuscator.py workspace-info --workspace <folder>`

Behavior:
- Prints artifact availability, mapping counts, batch/statement counts, created timestamps.

## LLM Instruction Artifact
Generate `llm_instructions.md` in workspace with strict guidance:
- script is obfuscated and will be de-obfuscated later,
- avoid introducing/removing identifiers unless necessary,
- preserve alias structure where possible,
- prefer structural optimizations,
- mark unavoidable new identifiers clearly.

## De-Obfuscation Strategy
1. Parse edited obfuscated SQL per batch.
2. Traverse AST and collect candidate identifier nodes with context.
3. Attempt reverse mapping by:
   - exact `obfuscated_lexeme` + `kind` + scope,
   - fallback to `obfuscated_lexeme` + nearest scope/role,
   - conflict detection if multiple candidates exist.
4. Restore original lexeme form using stored casing/bracketing flags.
5. Emit coverage report:
   - mapped identifiers
   - unknown obfuscated identifiers
   - new identifiers introduced by LLM
   - dropped identifiers expected from original mapping

## Validation and Safety Checks
- Parse validation before and after each transform step.
- Mapping collision checks (`obfuscated_lexeme` uniqueness per scope).
- Reserved keyword safety remains enforced.
- Deterministic mode tested with fixed seed.

## Testing Strategy
### Unit tests
- Mapping serialization/deserialization.
- Scope-aware reverse lookup.
- Casing/bracketing restoration.
- Alias-scope correctness (`table alias`, `projection alias`, `UPDATE alias`).

### Integration tests
- `obfuscate -> deobfuscate` identity for identifiers.
- LLM-like edited obfuscated scripts (query rewrite, extra predicates, join reorder).
- Unknown identifier handling in de-obfuscation report.
- Multi-batch (`GO`) scripts.

### Manual verification workflow (Windows)
- Run `roundtrip` command.
- Compare `original.sql` vs `deobfuscated.sql` in WinMerge.
- Expect identifier lexical fidelity; formatting may differ unless exact formatting preservation is later added.

## Known Limits (explicit)
- Strong lexical round-trip is targeted for identifiers, not full byte-for-byte file reconstruction.
- Comments/whitespace may still differ due to SQL regeneration.
- If LLM introduces entirely new identifiers, they cannot be "restored" to unknown originals.

## Implementation Phases

### Phase 1: Workspace + mapping persistence
- Add workspace artifact model and JSON schemas.
- Persist forward+reverse mapping with lexical fields.
- Keep current obfuscation behavior stable.

### Phase 2: CLI command split
- Add subcommands (`obfuscate`, `deobfuscate`, `roundtrip`).
- Preserve backward compatibility for current positional mode if feasible.

### Phase 3: Scope-aware de-obfuscator
- Implement reverse transformer with context matching.
- Add report generation.

### Phase 4: Roundtrip verification mode
- Implement immediate obfuscate+deobfuscate command.
- Add machine-readable and human-readable diff reports.

### Phase 5: Docs and examples
- README updates with full LLM workflow.
- Sample workspace and command recipes.

## Actionable Checklist

### A) Data model and persistence
- [ ] Define `mapping.json` schema (versioned).
- [ ] Define `context.json` schema (dialect, seed, batch/statement metadata).
- [ ] Implement mapping writer/reader modules.
- [ ] Add schema validation on load.

### B) Transformer instrumentation
- [ ] Emit mapping records during obfuscation for all renamed kinds.
- [ ] Capture original lexical details (case, brackets, temp prefixes).
- [ ] Capture scope metadata for alias-safe reverse mapping.

### C) CLI and workspace operations
- [ ] Implement `obfuscate` subcommand with workspace creation.
- [ ] Implement `deobfuscate` subcommand consuming workspace artifacts.
- [ ] Implement `roundtrip` subcommand.
- [ ] Add `workspace-info` subcommand (optional but recommended).
- [ ] Keep old CLI mode functional or provide explicit migration note.

### D) Reverse mapping engine
- [ ] Build AST-based reverse transformer.
- [ ] Implement scoped conflict resolution.
- [ ] Restore original lexical forms for identifiers.
- [ ] Emit de-obfuscation coverage/conflict report.

### E) LLM workflow support
- [ ] Generate `llm_instructions.md` in workspace.
- [ ] Add command-line option to customize instruction template.
- [ ] Add tests for expected instruction file content.

### F) Testing
- [ ] Add unit tests for mapping and lexical restoration.
- [ ] Add integration tests for full workflow with edited obfuscated SQL.
- [ ] Add regression tests for GO batches and alias edge cases.
- [ ] Add deterministic tests for saved mapping reproducibility.

### G) Documentation
- [ ] Update README with new command set and workspace layout.
- [ ] Add a "LLM optimization workflow" section with end-to-end steps.
- [ ] Add troubleshooting guide for unresolved identifiers.

### H) Optional future hardening
- [ ] Add mapping signature/checksum to detect workspace tampering.
- [ ] Add dry-run de-obfuscation mode.
- [ ] Add JSON report export for CI automation.

## Suggested First Delivery Slice
Deliver in this order for fast value and lower risk:
1. Workspace creation + mapping persistence (`obfuscate`).
2. Basic `deobfuscate` using reverse map with scope support.
3. `roundtrip` command + reports.
4. README and examples.
