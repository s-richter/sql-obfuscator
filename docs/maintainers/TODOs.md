# Maintainer Backlog

Open work should normally be tracked as GitHub issues. This file records items
that still need triage before becoming scoped issues.

## Needs Triage

### Obfuscation Error UX Audit

Review representative `obfuscate` failures and ensure each error explains:

- what failed
- whether output or workspace files were written
- the safest next action
- which report to inspect, when applicable

### Automated Sample-SQL Smoke Suite

Add parametrized smoke coverage for the tracked `sample_sql/*.sql` corpus.
Record the expected dialect and whether each script should fully transform,
use parser fallback, or fail validation.

### GUI

Use [the GUI implementation plan](plans/gui-implementation-plan-2026-03-01.md)
as the starting point. Convert the selected milestone into GitHub issues when
GUI work is prioritized.

## Optional Convenience Features

### External-LLM Clipboard Helper

Decide whether a helper command should prepare the files or prompt text needed
for copying an obfuscated script into an external LLM workflow.
