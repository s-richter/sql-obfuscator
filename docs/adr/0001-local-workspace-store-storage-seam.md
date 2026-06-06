# ADR 0001: Keep LocalWorkspaceStore as the Current Storage Seam

Date: 2026-06-06

## Status

Accepted

## Context

The workspace model has been separated from most local filesystem persistence. `workspace.py` now primarily owns schemas, payload validation, `WorkspaceSnapshot`, and compatibility wrappers. `LocalWorkspaceStore` owns local directory persistence, artifact layout, integrity validation, workspace inspection, safe artifact loading, and report persistence. `LocalWorkspaceApplication` composes host-neutral workflow results with this local persistence module.

The next architectural question is whether to introduce a full `WorkspaceStore protocol` before a second storage adapter exists.

## Decision

Defer a full `WorkspaceStore protocol` until there is a real second adapter. Keep `LocalWorkspaceStore` as the only concrete storage module for now, and keep local filesystem rules inside it.

`LocalWorkspaceApplication(store=...)` remains the application seam. New local persistence behavior should flow through `LocalWorkspaceStore` or `LocalWorkspaceApplication`, not through expanded filesystem logic in CLI command handlers.

## Consequences

This avoids freezing accidental filesystem assumptions into a speculative host-neutral interface. It also keeps the current module graph simpler while the only supported persistence adapter is local directory storage.

The cost is that the storage seam has less proof of leverage until another adapter exists. `Path`, relative artifact paths, integrity files, symlink safety, and local report directories remain part of the current persistence shape.

## Revisit Triggers

Revisit this decision when implementing a real second adapter, such as:

- web tenant storage
- desktop project storage
- another non-local adapter

At that point, introduce a storage protocol around the behavior both adapters actually share, and add contract tests that run against `LocalWorkspaceStore` and the new adapter.
