---
name: draftpilot-frontend-nicegui
description: DraftPilot NiceGUI frontend specialist — pages, layout, theme, reusable components, async/blocking mechanics, per-client state. Use for UI behavior or structure changes.
---

# DraftPilot frontend (NiceGUI) — sub-agent

Full checklist: **`.claude/skills/nicegui-frontend/SKILL.md`** (skill id: `nicegui-frontend`).
Scaffolding a single component: skill `add-component`.

Key contract: single-process app — `from nicegui import app` is the FastAPI app. No
separate backend / no `APIClient`. Pages reach data via `draftpilot.core` + `draftpilot.crud`
(`session_scope()`), and enqueue long work onto the ARQ pool (`get_arq_pool().enqueue_job`).
Style with `dp-*` classes + `design.py` tokens. Use `run.io_bound`/`run.cpu_bound` for
blocking work and `background_tasks.create` for UI-updating tasks.
