# Screenplay Ground-Test Benchmark Plan

## Objective

Validate DraftPilot against one writer-owned 165-page feature screenplay through both creative
redevelopment and production import/interoperability paths.

## Track A: redevelop from scratch

- Create an isolated benchmark project with a versioned premise and creative brief.
- Supply only high-level inputs: genre, audience, premise, constraints, and intended tone.
- Generate and snapshot canon, characters, outline, timeline, creative context, scenes, and draft.
- Run deterministic and human evaluation after each stage before proceeding.
- Record where the result diverges from the writer's intended story and whether the divergence is
  useful, neutral, or harmful.

## Track B: import and compare

- Keep the original Final Draft 13 FDX in an immutable control project and protected backup.
- Import into a separate working project with an import report and warnings.
- Compare page/scene counts, headings, blocks, characters, dialogue, transitions, dual dialogue,
  revisions, and metadata.
- Run context and review workflows against the imported screenplay without changing the control.
- Export FDX/PDF/Fountain from revisions and compare semantic and visual fidelity.

## Shared evaluation contract

- Store artifact manifests, model/provider settings, instruction layers, workflow runs, and named
  snapshots for every stage.
- Use mocked/fixture-backed browser tests; never use the developer's live Compose database as test
  state.
- Score story beats, character arcs, pacing, tone, visual language, continuity, format fidelity,
  export fidelity, and writer usefulness.
- Require explicit approval before applying agent changes and preserve rollback to the prior
  snapshot.

## Exit criteria

- Both tracks can be replayed from a clean project copy.
- The imported control remains byte-preserved and semantically recoverable.
- The benchmark produces a human-readable comparison report and machine-readable evaluation data.
- Failures identify whether the cause is import fidelity, context generation, agent reasoning,
  editing UX, permissions, or export behavior.
