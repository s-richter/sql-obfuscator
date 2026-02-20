# SQL Obfuscator + LLM Use Cases

This file lists practical use cases for the workflow:
1. Obfuscate SQL.
2. Send obfuscated SQL to an LLM.
3. Ask for analysis, edits, or generation.
4. De-obfuscate and validate results.

## 1. Explain and Understand Existing SQL

1. Summarize what a complex query does in plain language.
2. Explain join logic and why each table is needed.
3. Describe filter semantics and edge-case behavior.
4. Explain aggregation and grouping logic.
5. Explain window function behavior.
6. Explain CTE dependency chains.
7. Explain temporary table lifecycle and purpose.
8. Explain stored procedure step-by-step execution flow.
9. Identify likely business purpose of each statement block.
10. Produce a "data lineage" narrative from source tables to outputs.

## 2. Refactor for Readability and Maintainability

1. Reformat and structure long queries consistently.
2. Replace nested subqueries with clearer CTEs.
3. Split monolithic scripts into logical sections.
4. Standardize alias style and naming patterns.
5. Remove duplicated expressions via CTE reuse.
6. Extract repeated filters into shared CTE blocks.
7. Add safe, concise comments for complex sections.
8. Convert implicit joins to explicit `JOIN ... ON ...`.
9. Normalize statement ordering for readability.
10. Reduce "SELECT *" usage with explicit column lists.

## 3. Performance and Query Plan Improvements

1. Suggest index candidates based on predicates and joins.
2. Rewrite non-sargable predicates into sargable forms.
3. Push filters earlier to reduce row volume.
4. Remove unnecessary DISTINCT operations.
5. Optimize heavy aggregation queries.
6. Improve TOP / ORDER BY patterns.
7. Optimize temp-table usage versus CTE/materialization.
8. Propose partition-aware query changes.
9. Rewrite expensive scalar subqueries as joins.
10. Reduce duplicate scans and repeated computations.

## 4. Correctness and Bug Fixing

1. Detect likely logic bugs in joins (fan-out, missing keys).
2. Catch incorrect NULL handling.
3. Fix date boundary errors (`<` vs `<=`, time components).
4. Fix accidental Cartesian products.
5. Correct GROUP BY / aggregation mismatches.
6. Detect missing deduplication where required.
7. Identify flawed `NOT IN` behavior with NULLs.
8. Fix incorrect UNION vs UNION ALL usage.
9. Correct INSERT column-value mismatches.
10. Repair broken dependency order across batches.

## 5. Security and Governance

1. Detect SQL injection risk patterns in dynamic SQL.
2. Recommend parameterization patterns.
3. Flag dangerous broad permissions patterns.
4. Identify direct access to sensitive columns.
5. Add masking/tokenization transformations.
6. Add row-level filtering conditions.
7. Enforce least-privilege query behavior.
8. Flag ad hoc access to PII/PHI candidate fields.
9. Suggest audit logging insert statements.
10. Generate safer error-handling paths for procedures.

## 6. Compliance and Policy Alignment

1. Check script against naming standards.
2. Enforce data retention filters.
3. Add deletion/anonymization logic for privacy workflows.
4. Prepare variants for region-specific policy constraints.
5. Add explicit provenance columns in ETL steps.
6. Add controls for regulated data exports.
7. Mark and isolate high-risk transformations.
8. Generate compliance-oriented review notes.
9. Suggest policy checks for CI pipelines.
10. Produce evidence text for change approvals.

## 7. Data Quality and Validation

1. Generate row-count reconciliation checks.
2. Add null-rate and uniqueness checks.
3. Add referential integrity validation queries.
4. Add anomaly checks for outlier values.
5. Add schema drift detection checks.
6. Add duplicate detection and reporting.
7. Add freshness checks on source tables.
8. Add threshold-based data quality gates.
9. Generate exception tables for rejected records.
10. Create validation summaries for ETL runs.

## 8. Migration and Dialect Adaptation

1. Convert T-SQL patterns to another SQL dialect.
2. Replace dialect-specific functions with equivalents.
3. Convert temp-table patterns for target engines.
4. Convert procedural constructs to set-based alternatives.
5. Modernize legacy syntax for target platform.
6. Prepare migration scripts with compatibility notes.
7. Flag unsupported data types/functions early.
8. Produce side-by-side old/new query versions.
9. Add fallback variants for mixed environments.
10. Generate migration test scripts.

## 9. ETL/ELT Engineering

1. Generate incremental load variants.
2. Add watermark logic for late-arriving data.
3. Add idempotent merge/upsert patterns.
4. Convert full refresh logic to incremental logic.
5. Add slowly changing dimension handling.
6. Add staging-to-core transformation layers.
7. Optimize batch boundaries with `GO` sections.
8. Add retries/error capture tables.
9. Add run metadata columns and lineage tags.
10. Add rollback/compensation scripts.

## 10. Schema Evolution and DDL Changes

1. Suggest additive schema changes needed by new features.
2. Generate safe column backfill scripts.
3. Generate compatible index create/drop plans.
4. Add default constraints and check constraints.
5. Split wide tables or normalize structures.
6. Generate phased deployment SQL (expand/migrate/contract).
7. Produce rollback DDL.
8. Generate data migration verification SQL.
9. Add compatibility views during transition.
10. Identify breaking changes before release.

## 11. Reporting and Analytics Improvements

1. Build KPI query variants from current script.
2. Add period-over-period metrics.
3. Add cohort or funnel analysis queries.
4. Add dimension drill-down capabilities.
5. Optimize dashboard-serving SQL.
6. Create reusable reporting views.
7. Generate ad hoc slice-and-dice templates.
8. Add feature-engineering SQL for ML pipelines.
9. Improve metric definitions for consistency.
10. Create analyst-friendly query documentation.

## 12. Testing and QA Automation

1. Generate unit-test-like SQL assertions.
2. Generate snapshot comparison queries.
3. Generate synthetic test data inserts.
4. Add pre/post deployment validation scripts.
5. Add canary checks for production rollouts.
6. Build regression test packs for query changes.
7. Add deterministic seed datasets for CI.
8. Generate negative tests for edge conditions.
9. Add semantic equivalence checks between query versions.
10. Generate "expected result" scaffolding.

## 13. Documentation and Knowledge Transfer

1. Auto-generate README sections for SQL modules.
2. Produce change summaries for pull requests.
3. Produce data flow diagrams (text-based).
4. Generate runbooks for operations teams.
5. Generate onboarding notes for new engineers.
6. Produce table/column glossary candidates.
7. Produce known-risk and assumptions sections.
8. Generate troubleshooting guides for failed runs.
9. Generate release notes tied to SQL changes.
10. Summarize dependency impacts for downstream consumers.

## 14. LLM-Collaboration-Specific Use Cases

1. Ask LLM to preserve all obfuscated identifiers exactly while editing logic.
2. Ask LLM to only optimize performance and avoid semantic changes.
3. Ask LLM to introduce a feature while keeping schema stable.
4. Ask LLM to produce multiple alternatives with tradeoff notes.
5. Ask LLM to generate a "minimal diff" version of changes.
6. Ask LLM to annotate risky edits with explicit warnings.
7. Ask LLM to produce rollout-safe and rollback-safe versions.
8. Ask LLM to produce dry-run validation SQL with each change.
9. Ask LLM to avoid introducing unknown identifiers.
10. Ask LLM to align output with team SQL conventions.

## 15. Operational Workflow Use Cases

1. Human-in-the-loop SQL modernization with confidentiality safeguards.
2. Vendor/contractor review without exposing real schema names.
3. Cross-team collaboration on sensitive analytics logic.
4. LLM-assisted incident response query debugging on protected logic.
5. Parallel "what-if" rewrites for architecture decisions.
6. Rapid prototyping while preserving reversible mappings.
7. Safe external model usage when data model confidentiality matters.
8. Internal model evaluation with standardized obfuscated corpora.
9. Prompt iteration workflows using the same obfuscated baseline.
10. Repeatable review pipelines: obfuscate, edit, validate, de-obfuscate.

