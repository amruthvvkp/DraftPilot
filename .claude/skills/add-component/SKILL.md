---
name: add-component
description: Scaffold a new reusable React component for the DraftPilot studio (frontend/src) with typed props, accessible markup, CSS styling, and an e2e test. Use when adding a button, card, input, panel, or other shared UI building block.
---

# Add a reusable UI component

1. **Implement** `frontend/src/MyComponent.tsx` — a default-exported function component with a
   typed props object. Use semantic, accessible elements (`<button>`, `<label>`, `aria-label`,
   headings) so Playwright can find it by role/label.

   ```tsx
   type BadgeProps = { label: string; tone?: 'neutral' | 'warm' }

   export default function Badge({ label, tone = 'neutral' }: BadgeProps) {
     return <span className={`badge badge-${tone}`} role="status">{label}</span>
   }
   ```

2. **Style** it with class names in `frontend/src/styles.css` (or a feature sheet such as
   `timeline.css`, imported by the component). Reuse the existing CSS variables; don't hard-code colors inline.

3. **Data**: if it needs server data, add a typed function in `frontend/src/api.ts` using the shared
   `request<T>()` helper — components never call `fetch` directly.

4. **Use** it from the page/panel that needs it (e.g. `Workspace.tsx`, `App.tsx`).

5. **Test**: add or extend a journey in `tests/e2e/` that mocks the API with `page.route(...)` and
   asserts the component via `get_by_role` / `get_by_label`. Python test functions need a one-line
   docstring and type hints.

6. **Verify**: `npm --prefix frontend run build` (typecheck + build) and `uv run pytest tests/e2e`
   (stack on :9000; first run `uv run playwright install chromium`).

See the `web-frontend` skill for routing, serving, and API conventions.
