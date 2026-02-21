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
- Provide a “strict mode” default or a dedicated “validate-before-write” command path.
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
