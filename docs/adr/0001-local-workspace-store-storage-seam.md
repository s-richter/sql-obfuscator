# ADR 0001: Keep LocalWorkspaceStore as the Current Storage Seam

Date: 2026-06-06

## Status

Accepted, revisited 2026-06-06

## Context

The workspace model has been separated from most local filesystem persistence. `workspace.py` now primarily owns schemas, payload validation, `WorkspaceSnapshot`, and compatibility wrappers. `LocalWorkspaceStore` owns local directory persistence, artifact layout, integrity validation, workspace inspection, safe artifact loading, and report persistence. `LocalWorkspaceApplication` composes host-neutral workflow results with this local persistence module.

The next architectural question is whether to introduce a full `WorkspaceStore protocol` before a second storage adapter exists.

The website hosting guardrails now define the first concrete non-local hosting shape:
hosted workspaces use `tenant_id` plus opaque server-generated `workspace_id`, reject
caller-provided filesystem paths, treat SQL artifacts and mapping/context payloads as
sensitive, and run hosted work as isolated jobs with per-workspace mutation locks.

## Decision

Defer a full `WorkspaceStore protocol` until there is a real second adapter. Keep `LocalWorkspaceStore` as the only concrete storage module for now, and keep local filesystem rules inside it.

`LocalWorkspaceApplication(store=...)` remains the application seam. New local persistence behavior should flow through `LocalWorkspaceStore` or `LocalWorkspaceApplication`, not through expanded filesystem logic in CLI command handlers.

The first non-local adapter target is tenant web storage. When implementation starts,
introduce a `WorkspaceStore` protocol around behavior that both `LocalWorkspaceStore` and
tenant web storage actually share, not around the full local filesystem surface.

The tenant web storage workspace identity model is:

- `tenant_id`: authenticated tenant or account owner
- `workspace_id`: opaque server-generated workspace ID scoped to the tenant
- optional display name: user-facing metadata only, never a storage lookup key

The shared protocol should cover:

- save and load workspace snapshots
- validate or report workspace integrity status
- inspect workspace metadata, counts, privacy flags, and artifact inventory
- open cataloged artifact views
- load cataloged artifact content
- persist de-obfuscation artifacts and reports
- persist roundtrip reports and optional comparison artifacts
- persist translation artifacts and reports
- persist LLM workflow, privacy summary, and edit-application reports
- report written artifact identifiers in a host-neutral shape

The following behavior remains local-filesystem-specific unless the web adapter proves an
equivalent is needed:

- deriving default workspace paths from input filenames
- exposing concrete `Path` values to callers
- symlink escape checks
- local directory creation and cleanup
- `.obf` directory layout details
- local integrity file serialization details
- direct filesystem read/write error messages

## Consequences

This avoids freezing accidental filesystem assumptions into a speculative host-neutral interface. It also keeps the current module graph simpler while the only supported persistence adapter is local directory storage.

The cost is that the storage seam has less proof of leverage until another adapter exists. `Path`, relative artifact paths, integrity files, symlink safety, and local report directories remain part of the current persistence shape.

The revisit outcome gives future web work a concrete direction: tenant web storage is the
first adapter that should force a real protocol. Until that work begins, `LocalWorkspaceStore`
stays concrete and direct.

## Revisit Triggers

Revisit this decision when implementing a real second adapter, such as:

- web tenant storage
- desktop project storage
- another non-local adapter

At that point, introduce a storage protocol around the behavior both adapters actually share, and add contract tests that run against `LocalWorkspaceStore` and the new adapter.

## Minimum Contract Tests For Tenant Web Storage

When tenant web storage is implemented, shared contract tests must run against both
`LocalWorkspaceStore` and the tenant web adapter. At minimum, they should verify:

- save, load, inspect, and open a workspace
- load only cataloged artifacts
- reject unknown artifact identifiers
- report unavailable artifacts consistently
- preserve integrity or equivalent tamper-detection semantics
- persist privacy, LLM workflow, edit-application, de-obfuscation, roundtrip, and translation reports
- keep host-specific identifiers out of host-neutral workflow outcomes
- enforce tenant/workspace authorization in the tenant web adapter
- reject caller-provided filesystem paths in hosted flows
