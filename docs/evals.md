# Evals and usefulness

DraftPilot measures its writers' room in two ways:

- **Offline evals** check that the room's agents and workflows still work well after a change. They
  run `pydantic_evals` suites on the Big Fish screenplay against local LM Studio and compare the
  results with committed baselines.
- **Online measurement** checks whether the room is actually useful to *you*. For that it tracks
  which of its proposals you accept, how much of its writing you keep, and your thumbs up or down.

## Offline evals

```bash
uv run python -m draftpilot.evals                    # every suite, compared with its baseline
uv run python -m draftpilot.evals room_qa rewrite    # some suites
uv run python -m draftpilot.evals --save-baseline    # record new baselines after a reviewed change
```

The command exits non-zero when any suite regresses. A suite regresses when a task fails, or when its
assertion pass rate or any average score drops by more than `--tolerance` (default `0.15`) below the
baseline in `evals/baselines/<suite>.json`.

| Suite | What it runs | How it's judged |
|---|---|---|
| `room_qa` | The script editor answers five questions that only the script can answer: the second scene's heading, Will's wife, Will's mother, the witch's eye, and what the catfish took | Expected facts are mentioned; the agent read the project through its tools; an LLM judge compares the reply with the expected answer |
| `rewrite` | **Rewrite a scene** on two real scenes with different briefs, with at most one revision round | The result parses as a screenplay scene; it adds no speaking characters; a "shorter" brief actually shortens; the script doctor's final score; an LLM judge checks the brief was delivered in the characters' voices |
| `outline` | **Notes → outline** from fresh notes (a lighthouse story, not Big Fish) | Beat count and three-act coverage; the notes' elements appear; the script doctor's score; an LLM judge checks causality and fidelity to the notes |
| `continuity` | A **continuity pass** over two scenes after a timeline contradiction is planted (Will is 17 in 1987 but "35" in 1998) | The planted error is caught; no issue cites a scene outside the draft |

### Isolation

Every suite runs on a fresh Big Fish project in a throwaway SQLite database, with its own local
retrieval index built from LM Studio embeddings. Evals never touch your stack:

- live-sync events are dropped;
- background jobs are refused;
- retrieval is answered from the local index, never from the RAG service.

### Models

Evals use the `EVAL__` settings, which are the same ones as [testing](testing.md) Tier 1:

- `EVAL__CHAT_MODEL` sets the model under test.
- `EVAL__JUDGE_MODEL` sets the LLM judge.
- `EVAL__EMBEDDING_MODEL` sets the model that builds the retrieval index.

When a model setting is empty, the model LM Studio currently has loaded is used. A judge that is the
same model as the one it grades is lenient, so for baselines you trust, load a second model and set
`EVAL__JUDGE_MODEL`.

!!! warning "Run evals after every agent change"
    Any change to a role spec, prompt, tool or workflow must run the affected suites on LM Studio
    before it is committed. When quality changes on purpose, record new baselines with
    `--save-baseline` and commit them with the change.

## Online measurement

Open **Writers' room → How useful is the room?** to see usefulness per workflow. The same data is
available from `GET /api/v1/projects/{id}/insights`.

| Measure | Meaning |
|---|---|
| **Accepted** | Of the proposals you decided, the share you approved. A later rollback counts as a rejection |
| **Kept** | Of the blocks an approved proposal wrote, the share that still carry its authorship. When you edit a block, its authorship moves back to you, so this falls as you rewrite the room's words |
| **👍 / 👎** | Your feedback on finished runs |
| **Useful** | The mean of whichever of Accepted, Kept and the thumbs-up share are known |

Every finished workflow also runs **automatic checks**, the same deterministic evaluators the offline
suites use. For example, it checks that a rewrite parses as a scene, records the script doctor's
score, and confirms that a continuity pass cited only real scenes. The results appear on the run's
card.

Per role, the insights also report runs, failure rate, tokens and mean duration, all taken from each
agent run's record.

### Where the measures live

Every measure is computed from Postgres: proposals and their decisions, block authorship, feedback
rows and agent-run records. Nothing is pushed to an external trace store. To look at spans, turn on
telemetry (`OTEL__ENABLED=true`) and open the bundled Grafana (`--profile observability`). Agent-run
records keep their trace ids, so you can go from a run to its trace.
