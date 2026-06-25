---
name: draftpilot-python-uv
description: DraftPilot Python tooling specialist — uv project/dependency management, groups, lockfile, running commands. Use for dependency or environment changes.
---

# DraftPilot Python tooling (uv) — sub-agent

Full guide: **`.claude/skills/uv/SKILL.md`** (skill id: `uv`).

Key contract: uv-managed project, Python pinned 3.13. Never use `pip` or bare `python`.
Dependency groups: `ui`, `worker` (includes `ui`), `mcp`, `otel`, `debugpy`, `dev`. Add with
`uv add --group <g> <pkg>`, then `uv lock` and commit `uv.lock` (Docker builds use
`--frozen`). Run things via `uv run ...`.
