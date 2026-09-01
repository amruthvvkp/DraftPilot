# React Screenplay Workspace Implementation Plan

## Goal

Move opened projects from the React vault into a modern screenplay workspace while keeping the
existing NiceGUI editor available during migration. Establish the data boundary needed for
scene-aware editing, layered instructions, and future creative-context workflows.

## Scope

- Add a read-only workspace API returning a project, screenplay metadata, acts, and scenes.
- Route project cards to a React workspace instead of treating a project id as a screenplay id.
- Render a three-pane workspace shell: scene navigator, screenplay canvas, and context/instructions.
- Add project and scene instruction fields to the UI state without inventing persistence before
  their canonical models/API are designed.
- Use Python Playwright with intercepted API responses for browser acceptance; never use the
  developer's Compose database as test state.

## Exit criteria

- A project card opens `/projects/{project_id}` and displays its screenplay workspace.
- Empty and populated scene states are legible, responsive, and keyboard navigable.
- Current project, selected scene, and instruction context are represented in the UI.
- API and browser tests pass, frontend builds, and the existing Python gates remain green.
