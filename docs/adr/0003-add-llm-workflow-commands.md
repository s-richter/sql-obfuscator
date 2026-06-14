# Add LLM Workflow Commands

Add `prepare-for-llm` and `restore-from-llm` as workflow commands for the common external
LLM loop, while keeping lower-level commands available for expert and custom workflows.
`prepare-for-llm` creates the local workspace and shareable LLM artifacts with qualifier
obfuscation, comment stripping, literal redaction, and fail-closed validation enabled by
default; it defaults to reversible redaction because restoration is central to the primary
LLM-assisted edit workflow, with `--irreversible` available for one-way sharing.
`restore-from-llm` accepts bounded edit JSON, applies it, validates restoration, and writes
restored SQL only when validation passes or explicit override flags are used.
