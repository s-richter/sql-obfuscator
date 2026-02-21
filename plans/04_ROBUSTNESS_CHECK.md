# Robustness Check: LLM Obfuscate/De-obfuscate Workflow

## Goal Alignment
The app already matches the core intended workflow:

1. Obfuscate SQL before sharing with an LLM.
2. Allow LLM edits on obfuscated SQL.
3. De-obfuscate the edited output back to real table/column names.

Current implementation provides strong building blocks for this:
- AST-based obfuscation/de-obfuscation.
- Workspace artifacts and integrity checks.
- Dry-run diagnostics for unresolved mappings.
- Translation stage support for `tsql` and `hive`.

## Findings (Ordered by Impact)

### 1. Non-dry-run de-obfuscation can succeed even with unresolved mappings (High)
In current CLI behavior:
- `deobfuscate --dry-run` returns non-zero when `unknown_count` or `ambiguous_count` is non-zero.
- `deobfuscate` (non-dry-run) writes output and returns success without enforcing the same failure gate.

Risk:
- Users can get a "successful" run with partially unresolved identifiers, then execute unsafe or broken SQL.

Recommendation:
- Fail non-dry-run by default when unresolved mappings exist.
- Add explicit override flag (for advanced users), e.g. `--allow-unresolved`.

### 2. Privacy protection is identifier-focused only (High)
Obfuscation currently focuses on identifiers (tables, columns, aliases, etc.), not full content redaction.

Risk:
- Sensitive literals, business constants, or comments may still be exposed to the LLM.

Recommendation:
- Add optional redaction mode for literals/comments before LLM export.
- Keep de-obfuscation compatibility by storing reversible placeholders where needed.

### 3. Resolver robustness declines with heavy LLM rewrites (Medium)
Reverse mapping resolution uses obfuscated token + kind + limited scope hints.

Risk:
- Large structural rewrites by the LLM (alias reshaping, scope changes) increase ambiguous/unknown mappings.

Recommendation:
- Enrich mapping context (stronger scope fingerprints).
- Add stricter prompt guidance and automated checks before final de-obfuscation.

### 4. Safety depends on user discipline (`--dry-run`) (Medium)
The platform has safety diagnostics, but they are optional in practice.

Risk:
- Production workflow may skip dry-run and miss unresolved mapping warnings.

Recommendation:
- Provide a strict mode default or a `validate-before-write` command path.
- Document this as the recommended default in README examples.

### 5. Cross-dialect translation is useful but structural (Low/Expected)
Translation support is correctly isolated and report-driven, but semantic equivalence is not guaranteed.

Risk:
- A script can be parseable after translation but still behave differently at execution time.

Recommendation:
- Keep current behavior, but make this limitation explicit in user guidance and reports.

## Overall Assessment
The app is directionally strong and already usable for the intended LLM workflow.
The most important missing piece is **hard safety enforcement on non-dry-run de-obfuscation**.
Fixing that first would materially improve reliability with minimal complexity.

## Suggested Next Implementation Steps
1. Enforce unresolved-mapping failure in non-dry-run de-obfuscation by default.
2. Add optional `--allow-unresolved` escape hatch.
3. Add optional literal/comment redaction mode for LLM-bound SQL.
4. Improve resolver context to tolerate bigger LLM structural rewrites.

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

## Phased Rollout Recommendation
1. Phase 1 (low risk): `--strip-comments` + `--redact-literals` in `irreversible` mode.
2. Phase 2: add `reversible` mode with `redaction.json` and unresolved-redaction diagnostics.
3. Phase 3: optional policy-driven selective redaction rules.

## Recommendation
Ship AST-based redaction with `irreversible` mode first, and treat reversible restoration as a second milestone.
Do not use regex as the primary implementation strategy.

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
