---
icon: lucide/box
---

# Monty sandbox

!!! note "Experimental, and off by default"
    Monty is switched off unless you set `MONTY__ENABLED=true`. Nothing in the studio, the writers'
    room or the room workflows runs code through it yet. You can leave it off and lose nothing.

## What it is for

Agents sometimes need a few lines of code to glue results together, for example to count scenes per act, total a
runtime, reshape a list before a proposal. Running model-written code on your machine is risky, so
DraftPilot keeps that code behind Pydantic Monty (the `pydantic-monty` package), a minimal
Python interpreter with no access to anything outside itself.

Today Monty is the foundation for that, not a feature you use directly: DraftPilot ships the
sandbox, its limits and its audit trail, but no agent role or workflow calls it. Any caller is meant to use the audited entry point
described below, so every attempt shows up in the audit log.

## Settings

| Setting | Default | What it limits |
|---|---|---|
| `MONTY__ENABLED` | `false` | whether any code may run at all |
| `MONTY__MAX_CODE_CHARS` | `20000` | the length of the code |
| `MONTY__MAX_INPUT_ITEMS` | `100` | how many named inputs it may receive |
| `MONTY__MAX_DURATION_SECONDS` | `0.5` | how long one execution may run |
| `MONTY__MAX_OUTPUT_CHARS` | `20000` | how much printed output it may produce |

With Monty off, every attempt fails with "Monty execution is disabled" (and is still audited).
Approve a policy for who may run what before you enable it on a shared installation.

## Security limits

- No external lookups, filesystem mounts, OS callbacks, network clients, shell or process access.
  The code sees only the values passed to it.
- Code that is empty or too long, or that receives too many inputs, is refused before it runs.
- Execution runs in Monty's worker process with a per-session time limit; output beyond the limit
  stops the run.
- Inputs are passed as typed values. When named inputs are present, Monty's static type check is
  skipped (those names only exist at run time); the interpreter boundary and the resource limits
  still apply.

## The audit log

Every attempt, successful or not, writes an audit record to the project: its status, a SHA-256 hash
of the code, the number of inputs, the size of the output, the duration, an optional run id and a
shortened error message. **The code and the input values are never stored.**

Read the records for a project:

```text
GET /api/v1/projects/{project_id}/monty-executions
```

Over MCP, the `read_monty_executions` tool returns the same redacted records. It needs the
`monty.audit.read` grant on that project ([MCP integration](mcp.md)).

## For developers

Call `execute_glue_audited` (in `draftpilot.core.monty`) for every execution: it runs the code and
writes the audit record through the project-scoped CRUD layer, on success and on failure.
`execute_glue`, the lower-level executor, writes no audit and is meant only for isolated unit tests.
