# Website Hosting Guardrails

Date: 2026-06-06

## Purpose

This note records the minimum guardrails required before SQL obfuscation workflows are
exposed through a multi-user website or hosted API. It also identifies which hosting
decisions should inform the storage-seam revisit in ADR 0001.

## Decisions

### Workspace Identity

Hosted workspaces must use opaque server-generated workspace IDs. Callers must never
provide filesystem paths or path-like workspace identifiers.

Workspace identity is scoped by tenant:

- `tenant_id` identifies the owning tenant or account.
- `workspace_id` identifies one server-generated workspace inside that tenant.
- optional display names are metadata only and are never used for storage lookup.

This keeps hosted storage independent of local directory names and gives the future
storage adapter an authorization boundary: every artifact operation must prove both
tenant ownership and workspace membership.

### Sensitive Storage

Treat original SQL, mapping payloads, context payloads, redaction payloads, and LLM
instructions as sensitive data. Hosted logs, metrics, traces, and audit events must not
include SQL snippets, identifier values, literal values, mapping entries, or rendered LLM
instructions.

Artifact names, counts, byte sizes, status codes, and high-level workflow outcomes may be
logged when they do not contain user SQL content.

### Limits

Hosted adapters must reject oversized work before parsing or persisting whenever possible.
The initial limits should be conservative and configurable by deployment:

- maximum SQL input bytes
- maximum parsed statement count
- maximum generated artifact bytes
- maximum artifact count per workspace
- maximum report bytes
- maximum retained workspaces per tenant or user
- retention period for temporary workspaces

Limits that protect parser or runtime safety belong in the web adapter or job runner before
calling host-neutral workflows. Limits that describe the local `.obf` workspace format do not
belong in host-neutral workflow code.

### Execution Isolation

Hosted parsing and transformation should run as background jobs for non-trivial SQL. The job
runner must provide:

- per-job timeout
- memory cap
- cancellation
- per-workspace mutation lock
- deterministic cleanup or explicit failed-job state for partial artifacts

Multiple jobs may read the same workspace concurrently, but only one job may mutate a
workspace at a time.

### LLM-Safe Policy

Hosted external-sharing workflows must fail closed by default. `llm_safe` behavior should be
enabled for hosted sharing paths unless a product decision explicitly allows expert override.

If expert override is allowed later, it must be explicit, audited, and visible in workflow
reports. Blocked hosted workspaces may retain diagnostic reports, but externally shareable
artifacts must not be presented as approved.

## Layer Ownership

The web adapter owns tenant authentication, opaque workspace IDs, caller input validation,
and rejection of filesystem paths.

The job runner owns execution timeouts, memory caps, cancellation, cleanup, and workspace
mutation locks.

The storage adapter owns tenant-scoped artifact lookup, sensitive artifact persistence,
artifact byte limits, retention enforcement, and authorization checks for every workspace
operation.

The host-neutral workflow layer owns SQL transformation behavior, structured diagnostics,
privacy decisions, and workflow summaries. It should not learn about tenants, web sessions,
filesystem paths, or deployment-specific quotas.

## Impact On ADR 0001

These guardrails make tenant web storage the most concrete first non-local adapter if hosted
SQL workflows are the next product direction. That adapter should not expose `Path` values to
callers. It should use `tenant_id` plus opaque `workspace_id` as the workspace identity and
provide artifact operations that can be contract-tested against `LocalWorkspaceStore`.

If hosted SQL workflows are not next, ADR 0001 can remain unchanged and `LocalWorkspaceStore`
can stay the only concrete persistence module.

## Minimum Future Contract Tests

When a non-local storage adapter is implemented, run the shared storage contract against both
`LocalWorkspaceStore` and the new adapter. At minimum, the contract should verify:

- save, load, inspect, and open a workspace without leaking host-specific identifiers
- load only cataloged artifacts
- reject unknown artifact paths
- report unavailable artifacts consistently
- preserve integrity or equivalent tamper detection semantics
- persist privacy, LLM workflow, edit-application, de-obfuscation, roundtrip, and translation reports
- enforce tenant/workspace authorization for the non-local adapter
- reject caller-provided filesystem paths in hosted flows
