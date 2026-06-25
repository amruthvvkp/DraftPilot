---
name: add-component
description: Scaffold a new reusable NiceGUI UI component for DraftPilot and register it in the design system. Use when adding a button, card, input, panel, or other shared UI building block.
---

# Add a reusable UI component

1. **Implement** the helper in the right module under `src/draftpilot/ui/components/`
   (`buttons.py`, `cards.py`, `inputs.py`, or a new module). Style with `dp-*` CSS classes and the
   token variables in `static/styles.css` — never hard-code colors. Use Quasar props via `.props(...)`.

   ```python
   def badge(text: str, color: str = "primary") -> ui.element:
       return ui.badge(text, color=color).props("rounded")
   ```

2. **Export** it from `src/draftpilot/ui/components/__init__.py` (add to imports and `__all__`).

3. **Showcase** it in `src/draftpilot/ui/components/design_system.py` inside a `c.panel("...")` block
   so the living style guide documents it.

4. **Verify**: `uv run python -c "import draftpilot.ui.components as c; print(c.__all__)"` and open
   `/design-system` in the running app.

Tokens (colors, spacing, radii, fonts) live in `src/draftpilot/ui/theme/design.py` and the matching
CSS variables in `static/styles.css`. Add new tokens in both places.

Every new function/method gets a one-line Sphinx docstring and full type hints (interrogate enforces
100%; mypy must stay clean).
