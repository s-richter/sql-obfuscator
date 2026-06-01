# Robustness Check: LLM Obfuscate/De-obfuscate Workflow

## Goal Alignment
The app already matches the core intended workflow:

1. Obfuscate SQL before sharing with an LLM.
2. Allow LLM edits on obfuscated SQL.
3. De-obfuscate the edited output back to real table/column names.

Current implementation provides strong building blocks for this:
- AST-based obfuscation/de-obfuscation.
- Workspace artifacts and integrity checks.
- Dry-run diagnostics for unresolved and low-confidence mappings.
- Validation-first command path via `validate-before-write`.
- Translation stage support for `tsql` and `hive`.

## Findings (Ordered by Impact)

### 1. Non-dry-run de-obfuscation can succeed even with unresolved mappings (Addressed)
Current CLI behavior:
- `deobfuscate --dry-run` returns non-zero when unresolved identifiers/placeholders are found.
- `deobfuscate` (non-dry-run) fails by default when unresolved mappings are detected.
- Explicit override exists via `--allow-unresolved`.

Risk:
- Low residual risk when users do not use override flags.

Recommendation:
- Keep current default.
- Retain `--allow-unresolved` as an explicit advanced override.

### 2. Privacy protection is identifier-focused only (Addressed)
Obfuscation now supports optional literal/comment redaction with reversible restoration.

Risk:
- Residual risk remains when redaction is not enabled.

Recommendation:
- Keep current redaction modes and policy options (`all`, `strings-only`, `sensitive`).
- Keep using reversible mode only when literal restoration is required after LLM edits.

### 3. Resolver robustness declines with heavy LLM rewrites (Addressed with Residual Risk)
Resolver now uses enriched context and multi-pass matching with confidence diagnostics.

Risk:
- Very heavy structural rewrites can still produce unresolved or low-confidence mappings.

Recommendation:
- Keep multi-pass/context-based resolver and confidence diagnostics as default.
- Keep prompt guardrails and rewrite constraints in workspace guidance.

### 4. Safety depends on user discipline (`--dry-run`) (Addressed)
Default non-dry-run behavior now enforces:
- unresolved mapping gate (`--allow-unresolved` override required)
- low-confidence gate (`--allow-low-confidence` override required)

Risk:
- Residual risk is mainly tied to explicit override usage.

Recommendation:
- Keep strict-by-default behavior and explicit override flags (`--allow-unresolved`, `--allow-low-confidence`).
- Keep `validate-before-write` as the safe validation-first path in documented workflows.

### 5. Cross-dialect translation is useful but structural (Low/Expected)
Translation support is correctly isolated and report-driven, but semantic equivalence is not guaranteed.

Risk:
- A script can be parseable after translation but still behave differently at execution time.

Recommendation:
- Keep current behavior, but make this limitation explicit in user guidance and reports.

## Overall Assessment
The app is directionally strong and usable for the intended LLM workflow.
The original highest-risk gaps are now implemented end-to-end: unresolved/low-confidence safety gates, reversible/irreversible redaction, context-aware resolver matching, and a dedicated validation-first command path.
Primary remaining work is incremental hardening, semantic validation depth, and operational UX polish.

## Suggested Next Implementation Steps
1. Add optional semantic-drift validation (for example, statement-shape checks) in `validate-before-write`.
2. Expand rewrite-heavy regression fixtures to stress confidence scoring and ambiguous remapping paths.
3. Add report-level triage hints for low-confidence matches (recommended manual review targets by clause/object kind).
4. Add optional strict profile presets for privacy redaction (for example, preset bundles for policy + mode + comment handling).

## Draft: Privacy Redaction Design (Item 2)

## Decision Summary
- Recommendation: implement AST-based literal redaction plus comment stripping, with optional reversible mode.
- Regex-only redaction is not recommended for production privacy guarantees.

## Options

### Option A: Regex-based redaction
Approach:
- Apply regular expressions to replace quoted strings, numeric constants, and comments.

Pros:
- Fast to prototype.
- No AST traversal changes.

Cons:
- Fragile for escaped quotes, multiline strings/comments, dialect-specific literal forms, and edge syntax.
- High risk of corrupting SQL or missing sensitive values.
- Hard to reason about correctness.

Verdict:
- Acceptable only as a short-term stopgap, not as the default protection mode.

### Option B: Token/lexer-based redaction
Approach:
- Use tokenizer output (if available) to redact token classes (`STRING`, `NUMBER`, `COMMENT`).

Pros:
- More robust than regex.
- Lower implementation complexity than full AST context analysis.

Cons:
- Weaker semantic context than AST.
- Can still struggle with dialect quirks and reconstruction fidelity.

Verdict:
- Better than regex, but secondary to AST for this project.

### Option C: AST-based redaction (Recommended)
Approach:
- Parse with `sqlglot` and transform literal nodes and comment-bearing nodes in a controlled pass.

Pros:
- Most robust across SQL syntax forms.
- Works naturally with existing AST-based architecture.
- Easier to test deterministically.

Cons:
- Higher implementation effort.
- Requires careful handling for reversible restoration behavior.

Verdict:
- Best long-term and default option.

### Option D: Hybrid policy mode
Approach:
- AST pass plus policy rules to redact only sensitive literals based on context.

Pros:
- Better utility (less over-redaction).
- Enables domain-specific controls later.

Cons:
- Requires rule design and tuning.
- Higher complexity than baseline.

Verdict:
- Good follow-up phase after baseline AST redaction is stable.

## Proposed CLI Contract
Add optional flags to `obfuscate` and `roundtrip`:
- `--strip-comments`: remove SQL comments in LLM-bound output.
- `--redact-literals`: redact literal values in LLM-bound output.
- `--redaction-mode <none|irreversible|reversible>`:
  - default: `none` (backward compatible)
  - `irreversible`: safest and simplest for privacy
  - `reversible`: stores placeholder mapping for restoration

Notes:
- `roundtrip` should pass these through to keep behavior aligned with `obfuscate`.
- `deobfuscate` should restore literals only when reversible redaction metadata exists.

## Workspace Artifacts
When redaction is enabled:
- Add `redaction.json` (metadata + placeholder map + mode).
- Add `redaction.schema.json`.
- Include `redaction.json` in integrity tracking when mode is `reversible`.

## Behavioral Contract

### Irreversible mode
- Output sent to LLM has comments stripped and literals redacted.
- De-obfuscation restores identifiers only.
- Original literal values are intentionally non-recoverable from artifacts.

### Reversible mode
- Output sent to LLM contains deterministic placeholders.
- Workspace stores mapping required to restore values after de-obfuscation.
- If placeholder continuity breaks due to LLM rewrite, emit unresolved-redaction diagnostics similar to unresolved identifier mapping.

## Test Plan
- Unit: `tests/test_redaction.py`
  - strings, numbers, booleans, nulls, dates, multiline literals.
  - single-line and block comments.
  - batch-separated scripts (`GO`).
  - tsql and hive dialect coverage.
- CLI: `tests/test_cli.py`
  - `obfuscate --strip-comments --redact-literals` writes expected sanitized outputs.
  - reversible mode writes `redaction.json` and validates integrity.
  - deobfuscate with reversible mode restores literals when placeholders remain intact.
  - deobfuscate returns non-zero when reversible placeholders are unresolved (unless explicit override is added).
- Integration:
  - obfuscate(redaction enabled) -> LLM-like edit -> deobfuscate path validates expected behavior.

## Phased Rollout Recommendation (Status)
1. Phase 1 completed: `--strip-comments` + `--redact-literals` in `irreversible` mode.
2. Phase 2 completed: `reversible` mode with `redaction.json` and unresolved-redaction diagnostics.
3. Phase 3 completed (baseline): policy-driven redaction options (`all`, `strings-only`, `sensitive`).

## Recommendation
Keep AST-based redaction as the primary strategy and continue avoiding regex as the core privacy control.
Use policy-driven redaction and strict de-obfuscation validation as default operational guidance.

## Implementation Task List (Privacy Redaction)

### Milestone 1: CLI and Config Surface
- [x] Add CLI flags to `obfuscate` and `roundtrip` in `src/sql_obfuscator/cli.py`:
  - [x] `--strip-comments`
  - [x] `--redact-literals`
  - [x] `--redaction-mode <none|irreversible|reversible>` (default `none`)
- [x] Validate incompatible combinations early (for example, mode `none` with redaction flags should map to a clear behavior).
- [x] Pass redaction options through the obfuscation pipeline APIs.
- [x] Update command help text and README command examples.

### Milestone 2: Redaction Engine (Baseline)
- [x] Create `src/sql_obfuscator/redaction.py`.
- [x] Implement AST-based literal redaction using `sqlglot` expressions.
- [x] Implement comment stripping for LLM-bound output.
- [x] Support dialect-aware handling for `tsql` and `hive`.
- [x] Ensure output remains parseable and compatible with current obfuscation/de-obfuscation flow.

### Milestone 3: Workspace Artifacts
- [x] Add `redaction.json` write/load helpers in `src/sql_obfuscator/workspace.py`.
- [x] Add `redaction.schema.json` generation/validation.
- [x] Extend workspace save path to persist redaction metadata when enabled.
- [x] Extend integrity tracking to include `redaction.json` for reversible mode.
- [x] Update `workspace-info` to report redaction artifact presence.

### Milestone 4: Reversible Redaction Mode
- [x] Add deterministic placeholder generation strategy (stable per run, collision-safe).
- [x] Store placeholder-to-original mapping in `redaction.json`.
- [x] Restore literals during `deobfuscate` when reversible metadata exists.
- [x] Add unresolved-placeholder diagnostics and non-zero failure behavior (aligned with unresolved identifiers).
- [x] Add explicit override behavior only if needed (`--allow-unresolved` semantics alignment).

### Milestone 5: Testing
- [x] Add `tests/test_redaction.py` with unit coverage:
  - [x] string literals (escaped quotes, multiline)
  - [x] numeric/boolean/null/date-like literals
  - [x] single-line and block comments
  - [x] multi-batch scripts with `GO`
  - [x] both `tsql` and `hive`
- [x] Extend `tests/test_cli.py`:
  - [x] obfuscate with redaction flags writes expected sanitized output
  - [x] reversible mode writes redaction artifacts
  - [x] reversible restoration success path
  - [x] unresolved placeholder failure path
- [x] Add integration scenario in `tests/test_llm_workflow_integration.py` for redacted workflow.

### Milestone 6: Documentation and Guardrails
- [x] Update `README.md` with:
  - [x] redaction feature overview and limitations
  - [x] irreversible vs reversible behavior
  - [x] recommended secure workflow examples
- [x] Add troubleshooting entries for unresolved placeholders and integrity failures involving redaction artifacts.
- [x] Clarify that regex-only approaches are not used for primary privacy enforcement.

### Delivery Order
1. CLI surface + baseline irreversible redaction (`strip-comments`, `redact-literals`).
2. Tests for baseline behavior.
3. Reversible mode + artifacts + diagnostics.
4. Final docs and workflow guidance.

### Definition of Done
- [x] Baseline irreversible redaction works for `obfuscate` and `roundtrip` on `tsql` and `hive`.
- [x] Reversible mode fully restores literals when placeholders are preserved.
- [x] Unresolved placeholder cases fail with actionable diagnostics.
- [x] Workspace artifacts and integrity checks include redaction metadata as specified.
- [x] README and CLI help are consistent with actual behavior.
