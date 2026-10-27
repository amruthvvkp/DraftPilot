# References & credits

DraftPilot draws on prior art for both design inspiration and reused libraries. This page
records attribution and license context. Keep it current: when work draws on an external
tool, UI, or codebase, add it here — and never vendor code under a license incompatible
with this project's MIT license (e.g. GPL).

## Design inspiration

- **Final Draft** — the web interface (project vault, navigator + script + panels editor
  layout) inspires DraftPilot's shell and screenplay workspace. Inspiration only; no Final
  Draft code or assets are used. <https://www.finaldraft.com/>
- **Outline drag-and-drop** — the Outline page uses the browser's native HTML drag-and-drop
  plus keyboard controls; no third-party drag-and-drop library is used.

## Reused libraries

- **Pydantic Monty** — runtime for short-lived, model-generated Python that composes
  explicitly granted DraftPilot host functions. Experimental; its security model and supported
  Python subset are subject to change. No unrestricted machine access or third-party packages
  are assumed. <https://pydantic.dev/docs/monty/get-started/>

- **screenplay-tools** — Fountain ⇄ Final Draft (FDX) parsing/writing; the foundation of
  DraftPilot's import/export adapters. MIT, © Ian Thomas.
  <https://github.com/wildwinter/screenplay-tools>
- **screenplain** — evaluated as a possible PDF/HTML export backend; DraftPilot currently uses
  its own ReportLab PDF and safe self-contained HTML renderers. MIT, © Martin Vilcans.
  <https://github.com/vilcans/screenplain>

- **AG-UI protocol** — the chat dock speaks the Agent-User Interaction protocol; the server side is
  Pydantic AI's `pydantic_ai.ui.ag_ui` adapter, the client uses the protocol's TypeScript types.
  MIT. <https://docs.ag-ui.com>

- **Pydantic AI** — the only agent framework: role agents, durable agents on Temporal, evals
  (`pydantic_evals`) and the AG-UI adapter. MIT. <https://ai.pydantic.dev>
- **Temporal** — durable execution for every background job, room workflow and chat turn, through
  the Python SDK (`temporalio`). MIT. <https://temporal.io>
- **FastMCP** — the MCP server framework. Apache-2.0. <https://gofastmcp.com>
- **TipTap** — the Document script editor (Settings → Editor: Document) is built on TipTap's
  open-source core, React bindings and extensions (`@tiptap/core`, `@tiptap/react`, `@tiptap/pm`,
  bold, italic, underline, strike, undo/redo, placeholder). No TipTap Pro extensions or TipTap
  Cloud are used. MIT, © überdosis GbR. <https://tiptap.dev> · <https://github.com/ueberdosis/tiptap>
- **ProseMirror** — the editing toolkit under TipTap (schema, transactions, decorations, history).
  MIT, © Marijn Haverbeke. <https://prosemirror.net>
- **React Router** — client routing in the studio. MIT. <https://reactrouter.com>
- **TanStack Query** — the studio's data layer and cache. MIT. <https://tanstack.com/query>
- **react-markdown** — Markdown in chat replies. MIT. <https://github.com/remarkjs/react-markdown>

## Inspiration only — not used as code

- **Trelby** — a mature open-source screenplay editor whose data model and multi-format
  export informed our thinking. Licensed **GPLv2+** (© Osku Salerma and contributors);
  therefore **not** vendored or copied into DraftPilot. Referenced for ideas only.
  <https://www.trelby.org/>
