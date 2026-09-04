# Monty sandbox

DraftPilot keeps model-generated glue code behind the feature-gated Pydantic Monty adapter. It is
disabled by default and can be enabled only with explicit `MONTY__ENABLED=true` configuration.
Each execution has limits for code length, input count, runtime, and captured output. DraftPilot
does not provide Monty with external lookups, filesystem mounts, OS callbacks, network clients,
shell access, or process access.

The adapter uses Monty’s worker-process runtime and per-session duration limits. Inputs are passed
as typed host values; when injected names are present, Monty’s static type-check pass is skipped
because those names are supplied at runtime, while the interpreter boundary and resource limits
remain active. When a caller associates an execution with a project run, DraftPilot persists a
redacted audit record containing status, code hash, input/output counts, duration, and bounded
error text; raw code and input values are never stored. Approval policy is still required before
enabling this feature in a shared deployment.
