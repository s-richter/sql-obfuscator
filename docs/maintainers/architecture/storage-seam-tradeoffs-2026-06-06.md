# Storage Seam Tradeoffs

Date: 2026-06-06

## Purpose

This note records the current state of the workspace storage seam after comparing the June 1 architecture review with the codebase. It focuses on the tradeoff between introducing a real storage interface plus a second adapter, and continuing to use `LocalWorkspaceStore` as the concrete persistence module.

## Current State

The June 1 architecture review recommended separating the workspace model from filesystem persistence. The codebase has since moved in that direction:

- `src/sql_obfuscator/workspace.py` now primarily owns workspace schemas, payload validation, `WorkspaceSnapshot`, and compatibility wrapper functions.
- `src/sql_obfuscator/local_workspace_store.py` owns local directory persistence, artifact layout, integrity validation, workspace inspection, safe artifact loading, and report persistence.
- `src/sql_obfuscator/local_application.py` coordinates host-neutral workflow results with local workspace persistence.
- `src/sql_obfuscator/cli.py` delegates most persisted workflow sequencing through `LocalWorkspaceApplication`.

This means the local persistence module is now fairly deep. It hides a lot of local filesystem behavior behind a smaller interface than the CLI previously had to understand.

## Option 1: Real Storage Interface and Second Adapter

A real storage interface is most useful when there is an actual second adapter, such as web tenant storage, desktop project storage, or an in-memory store for tests. With two adapters, the seam becomes real instead of hypothetical.

Benefits:

- `LocalWorkspaceApplication` can depend on a smaller storage interface instead of a concrete local filesystem store.
- Local disk, web storage, desktop storage, and test storage can share the same application workflow.
- Contract tests can define the storage behavior once and run against every adapter.
- Host-specific storage choices stop shaping the application workflow by default.

Costs:

- The interface must define workspace identity, artifact identity, integrity semantics, missing artifact behavior, report persistence, and read-only artifact rules.
- A web or tenant adapter may not naturally fit the current `Path`-centered interface.
- If the second adapter is speculative, the interface may just mirror `LocalWorkspaceStore` and add ceremony without reducing complexity.
- Introducing a protocol too early can freeze accidental filesystem assumptions into a supposedly host-neutral interface.

## Option 2: Continue With `LocalWorkspaceStore`

Keeping `LocalWorkspaceStore` as the concrete module is cheaper and currently defensible. The module already earns its keep by concentrating local artifact rules and filesystem safety behavior.

Benefits:

- Lower implementation cost.
- Fewer abstractions for maintainers to understand.
- Current tests exercise the concrete behavior users actually rely on.
- The local workspace format can continue to evolve without maintaining a premature adapter contract.

Costs:

- Local filesystem assumptions remain the default shape of the application.
- `Path`, relative artifact paths, integrity files, symlink safety, and local report directories are still embedded in the persistence interface.
- A future web adapter may require refactoring under pressure if it cannot share those assumptions.
- Without a second adapter, the storage seam has less proof of leverage.

## Recommendation

Do not introduce a full storage interface until a second adapter is real. The current `LocalWorkspaceStore` is deep enough to keep as the only concrete storage module for now.

The next practical step is to preserve the current seam shape:

- keep `LocalWorkspaceApplication(store=...)` as the application seam
- keep local filesystem rules inside `LocalWorkspaceStore`
- avoid spreading direct local workspace artifact rules back into `cli.py` or `workflow.py`
- introduce a `WorkspaceStore` protocol only when a second adapter is being implemented
- add contract tests at that point and run them against both `LocalWorkspaceStore` and the second adapter

This keeps the design ready for a real seam without paying for a hypothetical one today.
