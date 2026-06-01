# LLM Workflow Architecture Recommendations

Date: 2026-03-22

## Purpose

This document evaluates whether the current `sql-obfuscator` architecture is a good fit for the intended workflow:

1. Obfuscate a SQL script.
2. Send the obfuscated script to an LLM.
3. Receive an edited obfuscated script back.
4. De-obfuscate the edited result safely.

It summarizes the strengths of the current design, identifies the main architectural risks, lists several viable ways forward, and recommends a practical approach for this repository.

## Executive Summary

The current architecture is appropriate for a bounded-edit workflow, but it is not the ideal long-term architecture for a free-form rewrite workflow.

Today the system works best when the LLM:

- keeps obfuscated identifiers intact
- preserves most statement and alias structure
- makes local changes such as predicate tweaks, projection changes, `DISTINCT`, filtering, or limited refactoring

The current system is much less reliable when the LLM:

- inserts, removes, or reorders statements
- rewrites alias structure or CTE hierarchy heavily
- invents new identifiers
- returns broadly restructured SQL rather than a constrained edit

The most important recommendations are:

- keep the current engine, but position it explicitly as a bounded-edit workflow
- harden the current full-script workflow with fail-closed privacy and coverage checks
- move toward a patch-based or statement-scoped edit contract as the recommended production workflow

Recommendation in one sentence:

- Near term: adopt a hardened version of the current workflow
- Medium term: make patch-based bounded edits the primary LLM integration path

## Current Architecture

The current design has several strong building blocks:

- `src/sql_obfuscator/pipeline.py`
  - parses SQL
  - applies AST-based identifier obfuscation
  - stores mapping and context metadata
- `src/sql_obfuscator/registry.py`
  - records mapping occurrences with structural context
- `src/sql_obfuscator/deobfuscation.py`
  - performs reverse lookup using exact and heuristic matching
  - emits unknown, ambiguous, and low-confidence diagnostics
- `src/sql_obfuscator/redaction.py`
  - supports literal redaction, including reversible placeholders
- `src/sql_obfuscator/workspace.py`
  - persists artifacts, instructions, reports, and integrity metadata
- `src/sql_obfuscator/cli.py`
  - exposes validation-first workflows such as `deobfuscate --dry-run` and `validate-before-write`

This is a good architecture for:

- deterministic obfuscation
- workspace-centered review and traceability
- restoring identifiers after constrained edits
- catching obvious safety failures before writing de-obfuscated output

## What the Current Design Gets Right

### 1. AST-based obfuscation is the right foundation

Using parsed SQL and AST-aware transforms is the correct base architecture. It is significantly safer than regex-only substitution and gives the project a reasonable path toward richer validation and reporting.

### 2. Validation is treated as a first-class concern

The project already has a good safety model:

- `unknown`
- `ambiguous`
- `low-confidence`
- reversible redaction placeholder diagnostics
- workspace integrity checks

This is exactly the kind of guardrail an LLM-facing tool should have.

### 3. The workspace model is strong

Persisting `mapping.json`, `context.json`, integrity metadata, and reports gives the workflow auditability and reproducibility. That is useful both for debugging and for cautious production use.

### 4. The generated LLM instructions are directionally correct

The default instructions already push the model toward:

- keeping obfuscated identifiers unchanged
- keeping alias structure stable
- avoiding large structural rewrites
- preserving placeholder literals

That is an appropriate behavioral contract for the current engine.

## Main Architectural Concerns

### 1. Reverse restoration is structurally coupled to the original script

The de-obfuscation resolver does not merely map one token back to one original token. It uses contextual metadata such as:

- batch index
- statement index
- scope id
- parent kind
- role
- clause kind
- statement kind
- node kind
- argument key

This is powerful for bounded edits, but it means restore quality depends on the edited SQL still resembling the original structural layout.

Consequences:

- harmless-looking statement insertion can reduce confidence
- alias reshaping can make restores ambiguous
- larger LLM refactors can move the script outside the resolver's reliable operating range

This is why the existing low-confidence behavior is not a bug in itself. It is a signal that the workflow contract has been stretched.

### 2. Full-script regeneration gives the LLM too much freedom

The current human-facing workflow asks the LLM to return an entire edited SQL script. That is convenient, but it also creates avoidable risk:

- the model can reorder statements
- the model can normalize or rewrite aliases
- the model can rewrite placeholders
- the model can introduce new names
- the model can change parts of the script that did not need to change

The more freedom the LLM has in the response format, the more work the resolver must do later to infer intent and recover identity.

### 3. Privacy is not fully fail-closed for all procedural T-SQL cases

This is the most important architectural concern.

The parser compatibility layer in `src/sql_obfuscator/sqlglot_compat.py` can preserve some advanced procedural T-SQL statements as raw SQL using `raw_sql` metadata. Those statements are then skipped by the normal AST transform path.

That is reasonable as a parser-compatibility technique, but it creates a risk for LLM-sharing workflows:

- some statements may pass through without full identifier obfuscation
- reversible or irreversible literal redaction may not cover the full privacy surface of those statements
- users may believe the script is safe to share when parts of it were only preserved, not fully transformed

For a local utility this may be acceptable with strong warnings. For a privacy-sensitive LLM workflow, this should not be the default behavior.

### 4. `Obfuscated` does not mean `all identifying information removed`

By design, the tool does not rename everything. For example, it preserves:

- schema qualifiers
- variables
- function invocation names

That may be the right SQL behavior, but it means the privacy promise must stay narrow. In some environments, schema names, function names, or variable names are themselves sensitive.

### 5. Heuristic recovery is helpful, but it should not be the primary safety strategy

Low-confidence recovery is a useful fallback. It should remain available.

However, the product should not rely on heuristic reconstruction as the main solution to LLM freedom. A better workflow is one that reduces the need for heuristics in the first place.

## Evaluation Criteria For Alternative Approaches

To choose a better long-term workflow, the main criteria should be:

- privacy safety when sharing with an external LLM
- robustness to realistic LLM edits
- ease of explaining the workflow to users
- compatibility with the current codebase
- implementation complexity
- ability to audit and validate output

## Possible Approaches

### Option 1: Keep the current workflow and mostly improve docs and prompts

#### Description

Keep the existing full-script input and output model, but clarify that the workflow is only intended for bounded edits. Improve `README.md`, `llm_instructions.md`, and troubleshooting guidance.

#### What would change

- stronger wording that the LLM should preserve identifiers and structure
- clearer explanation that low-confidence is expected after heavy rewrites
- clearer positioning of the tool as a constrained edit pipeline, not a free-form refactor engine

#### Benefits

- lowest implementation cost
- no workflow migration for existing users
- preserves current CLI and test model

#### Risks

- the underlying privacy and structural fragility remain
- users may still treat the tool as safe for broader rewrite use cases
- heavy-edit failures still happen at the end of the process rather than being prevented up front

#### Effort

- Low

#### Verdict

Useful, but not sufficient on its own.

### Option 2: Keep the full-script workflow, but harden it significantly

#### Description

Retain the current full edited script model, but add fail-closed checks, better coverage reporting, and a clearer distinction between safe and expert modes.

#### Suggested changes

- add an LLM-safe mode that refuses output when any statement had to use raw passthrough or parser fallback beyond approved forms
- produce an obfuscation coverage report
- report how many statements were fully transformed versus preserved through fallback
- warn or fail when unrenamed identifier classes remain in the output, depending on mode
- add a dedicated privacy summary to the workspace
- add richer restore diagnostics so users can see exactly which statements or identifier kinds caused low-confidence
- consider stronger stable anchors for statements or identifiers to reduce restore fragility

#### Benefits

- preserves existing workflow shape
- improves trustworthiness immediately
- directly addresses the largest privacy concern
- keeps compatibility with current code and tests

#### Risks

- still relies on full-script regeneration by the LLM
- still vulnerable to larger structural rewrites
- heuristics remain necessary

#### Effort

- Medium

#### Verdict

This is the best near-term improvement path and should be done regardless of longer-term direction.

### Option 3: Move to a patch-based bounded edit workflow

#### Description

Instead of asking the LLM to return a complete SQL script, ask it to return edits against the obfuscated SQL.

Possible response formats:

- unified diff
- statement-level replace operations
- JSON patch-like operations
- a simple custom schema such as `replace statement X with Y`

The tool would then:

1. validate the patch format
2. apply the patch to the obfuscated SQL
3. run the same de-obfuscation and validation pipeline

#### Benefits

- much less structural drift
- unchanged parts of the script stay untouched
- placeholders and untouched identifiers are more likely to survive intact
- easier audit trail
- easier to explain which changes the LLM actually made
- lower dependence on heuristic restore logic

#### Risks

- requires new tooling and prompt design
- some LLMs are inconsistent at producing high-quality diffs unless prompted carefully
- complex multi-location refactors may still be awkward

#### Effort

- Medium to High

#### Verdict

This is the best long-term product fit for the stated goal.

### Option 4: Use statement-scoped or region-scoped editing instead of full-script editing

#### Description

Split the script into stable units, assign IDs, and ask the LLM to return replacements only for selected statements or regions.

Examples:

- `replace statement 4`
- `replace statements 7 and 8`
- `return JSON with edited text for region IDs`

#### Benefits

- much safer than full-script regeneration
- simpler than arbitrary diff parsing
- works well for many SQL tuning and cleanup tasks
- easier to validate that untouched parts remain untouched

#### Risks

- cross-statement refactors become harder
- region boundaries must be chosen carefully
- still allows drift within each region

#### Effort

- Medium

#### Verdict

A strong alternative if patch-based diff workflows feel too heavy. This could also be a stepping stone toward patch-based editing.

### Option 5: Use the LLM only for intent, then apply deterministic AST transforms locally

#### Description

Instead of asking the LLM to write SQL, ask it to describe desired transformations, and let deterministic code apply them to the AST.

Examples:

- add a filter
- change an inner join to a left join
- add `DISTINCT`
- move a predicate

#### Benefits

- strongest safety profile
- best auditability
- minimizes privacy leakage from regenerated SQL

#### Risks

- much narrower scope
- high implementation complexity
- many real SQL edits are too open-ended for a small deterministic transformation language

#### Effort

- High to Very High

#### Verdict

Interesting for a future specialized optimizer mode, but not the right primary recommendation now.

## Comparison Summary

| Option | Privacy Safety | Robustness To Heavy LLM Rewrites | Backward Compatibility | Implementation Effort | Overall Fit |
|---|---|---|---|---|---|
| 1. Docs/prompt hardening only | Low | Low | High | Low | Weak alone |
| 2. Harden current full-script workflow | Medium | Low to Medium | High | Medium | Strong near-term |
| 3. Patch-based bounded edits | High | Medium to High | Medium | Medium to High | Best long-term |
| 4. Statement or region-scoped edits | High | Medium | Medium | Medium | Strong alternative |
| 5. Intent-to-AST transforms | Very High | High within narrow scope | Low | High | Niche future mode |

## Recommended Approach

### Recommendation

Adopt a combined strategy:

1. Near term: Option 2
2. Target architecture: Option 3
3. Optional intermediate step: Option 4

In practical terms:

- keep the current workflow available
- harden it immediately
- stop treating full-script LLM regeneration as the ideal path
- introduce a more constrained edit contract as the preferred workflow

### Why this is the best fit

#### It keeps the current investment

The current codebase already has strong components:

- AST transforms
- workspace persistence
- restore diagnostics
- validation and reporting

None of that needs to be discarded.

#### It addresses the biggest real risks first

The most urgent issues are:

- privacy ambiguity when parser fallback preserves raw SQL
- users overestimating how much freedom the LLM can safely take

Option 2 addresses those without requiring a redesign first.

#### It moves the product toward a more stable contract

Patch-based editing reduces the amount of intent the tool has to reconstruct afterward. That is the core architectural improvement this workflow needs.

## Recommended Product Positioning

The project should describe itself more explicitly as one of these:

- a bounded-edit SQL optimization workflow
- a safe obfuscate-edit-restore pipeline for constrained LLM edits

It should avoid implying:

- safe arbitrary SQL rewrite recovery
- complete privacy across every T-SQL construct
- semantic equivalence under large free-form restructures

## Recommended Implementation Plan

### Phase 1: Harden the current workflow

#### Goals

- make privacy guarantees clearer
- fail closed in unsafe LLM-sharing cases
- improve diagnostics

#### Suggested deliverables

- add an LLM-safe mode such as `--llm-safe` or `--fail-on-fallback`
- emit a workspace report summarizing:
  - total statements
  - fully transformed statements
  - fallback-preserved statements
  - redacted literal counts
  - unresolved, ambiguous, and low-confidence counts
- fail or warn clearly when fallback-preserved statements exist in LLM-sharing mode
- add tests that prove unsafe fallback cases are surfaced clearly
- update `README.md` and `llm_instructions.md` to distinguish bounded-edit mode from expert mode

#### Result

The current workflow becomes safer and easier to trust, even before changing the edit contract.

### Phase 2: Introduce stable edit anchors

#### Goals

- reduce restore fragility
- prepare for constrained edit workflows

#### Suggested deliverables

- assign stable statement IDs in workspace metadata
- optionally record statement fingerprints or region IDs
- expose those IDs in generated LLM instructions
- extend reporting so low-confidence or unresolved issues identify the affected statement IDs directly

#### Result

The system gains a stable unit of change that is less brittle than raw position alone.

### Phase 3: Add a patch-based or statement-replacement workflow

#### Goals

- reduce LLM freedom
- reduce restore heuristics
- improve auditability

#### Suggested deliverables

- add a new command such as `apply-llm-edits` or `apply-patch`
- support one constrained response format first
- validate that edits only target known statement IDs or valid patch hunks
- preserve untouched obfuscated SQL exactly
- reuse existing de-obfuscation and validation after patch application

#### Result

This becomes the recommended production workflow for external LLM use.

### Phase 4: Keep full-script regeneration as a legacy or expert workflow

#### Goals

- preserve backward compatibility
- keep power-user flexibility
- avoid overstating guarantees

#### Suggested deliverables

- keep existing `deobfuscate` support for full edited scripts
- mark it as advanced or expert mode in docs
- require dry-run validation as the standard workflow
- keep `--allow-low-confidence` and `--allow-unresolved` as explicit manual override paths

#### Result

Existing users are not broken, but the safer path becomes the default recommendation.

## Concrete Recommendation For This Repository

If only one path should be prioritized, it should be:

- implement Option 2 now
- plan Option 3 as the strategic direction

If a single explicit recommendation is needed for architecture choice:

- Recommended architecture: hardened current engine plus a new patch-based LLM edit contract

This balances:

- safety
- engineering cost
- reuse of current code
- backward compatibility
- product clarity

## What Not To Recommend Right Now

The following would not be my primary recommendation today:

- relying on documentation changes alone
- assuming heuristic low-confidence resolution is sufficient for broad rewrite use cases
- marketing the current workflow as safe for arbitrary SQL rewrites
- attempting a full intent-to-AST transformation engine before tightening the edit contract

## Success Criteria

The recommended direction is working if:

- LLM-safe mode can tell users clearly whether a script is shareable
- fallback-preserved statements are visible and actionable
- most production LLM edits no longer trigger low-confidence due to avoidable structural drift
- the preferred workflow preserves untouched SQL exactly
- override flags are rare rather than routine

## Final Recommendation

The current architecture is worth keeping, but it should be treated as the core of a constrained-edit system, not as the final architecture for unconstrained LLM rewrites.

The best path for this project is:

- harden the current full-script workflow immediately
- then move the recommended LLM interaction toward patch-based bounded edits

That approach gives the repository a realistic, safer, and more defensible long-term design without throwing away the strong engineering already in place.
