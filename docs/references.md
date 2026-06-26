# References & credits

DraftPilot draws on prior art for both design inspiration and reused libraries. This page
records attribution and license context. Keep it current: when work draws on an external
tool, UI, or codebase, add it here — and never vendor code under a license incompatible
with this project's MIT license (e.g. GPL).

## Design inspiration

- **Final Draft** — the web interface (project vault, navigator + script + panels editor
  layout) inspires DraftPilot's shell and screenplay workspace. Inspiration only; no Final
  Draft code or assets are used. <https://www.finaldraft.com/>
- **NiceGUI** Trello-cards example — reference for the planned beat-board drag-and-drop.
  MIT. <https://github.com/zauberzeug/nicegui>

## Reused libraries

- **screenplay-tools** — Fountain ⇄ Final Draft (FDX) parsing/writing; the foundation of
  DraftPilot's import/export adapters. MIT, © Ian Thomas.
  <https://github.com/wildwinter/screenplay-tools>
- **screenplain** — planned PDF/HTML export backend (deferred). MIT, © Martin Vilcans.
  <https://github.com/vilcans/screenplain>

## Inspiration only — not used as code

- **Trelby** — a mature open-source screenplay editor whose data model and multi-format
  export informed our thinking. Licensed **GPLv2+** (© Osku Salerma and contributors);
  therefore **not** vendored or copied into DraftPilot. Referenced for ideas only.
  <https://www.trelby.org/>
