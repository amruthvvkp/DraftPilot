# React Screenplay Workspace Implementation Plan

## Goal

Move opened projects from the React vault into a modern screenplay workspace while keeping the
existing NiceGUI editor available during migration. Establish the data boundary needed for
scene-aware editing, layered instructions, and future creative-context workflows.

## Visual reference

Use the page wireframes in [`draftpilot-pages.html`](../wireframes/draftpilot-pages.html) as the
layout reference for the next surfaces. The existing project vault and screenplay workspace are
the visual anchors; the other views show the intended information hierarchy for project overview,
story development, agents/review, and settings/export.

## Scope

- Add a read-only workspace API returning a project, screenplay metadata, acts, and scenes.
- Route project cards to a React workspace instead of treating a project id as a screenplay id.
- Render a three-pane workspace shell: scene navigator, screenplay canvas, and context/instructions.
- Add project and scene instruction fields to the UI state without inventing persistence before
  their canonical models/API are designed.
- Use Python Playwright with intercepted API responses for browser acceptance; never use the
  developer's Compose database as test state.
- Reserve the first end-to-end screenplay benchmark for two isolated tracks: rebuild the writer's
  feature from high-level inputs without screenplay text, then import the immutable Final Draft
  13 FDX control and compare structure, fidelity, context, and revisions.

## Exit criteria

- A project card opens `/projects/{project_id}` and displays its screenplay workspace.
- Empty and populated scene states are legible, responsive, and keyboard navigable.
- Current project, selected scene, and instruction context are represented in the UI.
- API and browser tests pass, frontend builds, and the existing Python gates remain green.
- The benchmark contract is documented before using the real screenplay: source control project,
  from-scratch project, artifact manifests, rubric, snapshots, and comparison outputs.
