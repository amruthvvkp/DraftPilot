---
icon: lucide/network
---

# Context workflows

A context workflow asks one specialist to develop a piece of creative context for your project — a
camera plan, a lighting plan, a colour palette, a continuity pass — from material you already have.
It comes back as a **suggestion with citations** for you to read. Nothing changes until you apply
it.

## Where to find them

Open the **Knowledge graph** page. Two ways in:

- from the **Script** page, the **Creative context** links in the right-hand rail: **＋ Knowledge
  graph**, or a shortcut that opens it ready to add a **Reference scene**, **Color palette**,
  **Camera & lighting** or **Film / director / style** node;
- from the address bar, `/projects/<id>/context`.

The page holds your canon (nodes and the links between them), your **Visual language** references,
and, below them, the **Context workflows** panel.

## Run one

1. Pick a **Workflow**.
2. Pick a **Source artifact**. The list shows only the artifacts that workflow can read. If it is
   empty, create a suitable artifact in the **Story studio** first.
3. Write an **Instruction**: what the agent should develop or check.
4. Press **Generate review suggestion**.

The panel shows the run's number, status and attempt count while it works, and retries a failed
attempt on its own. If you leave the page, the run carries on in the background and its result is
stored with the run (the panel itself shows only the run you started from it). When it succeeds you
see the suggestion and whether citations were attached.

| Workflow | Reads | Who works on it |
|---|---|---|
| **Reference scene** | brief, outline, character, canon | researcher |
| **Visual language** | brief, outline, canon | associate director |
| **Camera plan** | brief, outline, timeline | associate director |
| **Lighting plan** | brief, outline, style | associate director |
| **Color palette** | brief, outline, style, reference scene | associate director |
| **Film, director, and style research** | brief, outline, reference | researcher |
| **Continuity pass** | brief, outline, character, timeline, canon | continuity supervisor |

## Apply it

Read the suggestion. If you want it, press **Apply to knowledge graph**: it becomes a new, versioned
node in your canon (named, for example, "Camera from run 12") that records the run, the source
artifact and version, and the citations it came from, and the panel says **Applied as
a new versioned graph node.** You can edit that node like any other.

!!! note "Applying is checked"
    A suggestion can be applied once. If the source artifact has changed since the run started,
    applying is refused, so canon never rests on an outdated source. Run the workflow again.

## From the API

The catalog and runs live under `/api/v1/projects/{project_id}/context/workflows`. The catalog
declares each workflow's accepted artifact kinds, output kind, evaluator, agent role and default
permission mode.

Start a run with `POST .../runs`, giving the `workflow`, a compatible `artifact_id` and an
`instruction`. The API saves a `context_generation` run and starts it on Temporal; the worker
retrieves project-scoped citations through the RAG service and calls the configured provider. A
successful result holds the suggestion, the citations, the source artifact version, the output kind
and the evaluator contract. The run is review-only: it never changes artifacts or graph nodes. Poll
`GET /api/v1/projects/{project_id}/runs/{run_id}` after a disconnect.

Apply a completed run with `POST .../runs/{run_id}/apply` and `{"expected_source_version": 4}`. The
server creates the provenance-linked graph node, records it on the run, and refreshes retrieval.
Reapplying a run, or applying against a changed source version, answers `409`.

Over MCP, `start_context_workflow` needs the `context.generate` grant, and `apply_context_workflow`
needs `context.apply` plus a writer-approved `approval_id` ([MCP integration](mcp.md#context-workflows)).
No API key or provider credential is ever sent to the browser.
