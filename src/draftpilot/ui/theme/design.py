"""Centralized design tokens for the DraftPilot studio UI.

Colors are defined once and exposed both to Quasar (via ``ui.colors``) and to
CSS custom properties (see ``ui/static/styles.css``). Spacing/radius/typography
tokens are kept as plain constants used across the reusable component library.
"""

# --- Brand palette (neutral greyscale shell + clapperboard-amber accent) --------
# Primary accent — "clapperboard amber" used for primary actions; everything else
# (headers, menus, surfaces) stays neutral white/grey for a modern, sleek look.
PRIMARY = "#e0a458"
SECONDARY = "#5b8fb9"
ACCENT = "#b56576"
POSITIVE = "#4caf82"
NEGATIVE = "#e06c75"
WARNING = "#e0a458"
INFO = "#5b8fb9"

# Quasar dark-page surfaces (neutral dark grey; consumed via CSS vars in styles.css).
DARK_PAGE = "#1a1a1c"
DARK_SURFACE = "#242427"

# --- Typography ----------------------------------------------------------------
FONT_SANS = "'Inter', system-ui, -apple-system, sans-serif"
FONT_MONO = "'JetBrains Mono', ui-monospace, monospace"

# --- Spacing scale (rem) -------------------------------------------------------
SPACE_XS = "0.25rem"
SPACE_SM = "0.5rem"
SPACE_MD = "1rem"
SPACE_LG = "1.5rem"
SPACE_XL = "2.5rem"

# --- Radii ---------------------------------------------------------------------
RADIUS_SM = "6px"
RADIUS_MD = "10px"
RADIUS_LG = "16px"


def quasar_colors() -> dict[str, str]:
    """Color kwargs passed to ``ui.colors`` to brand Quasar components."""
    return {
        "primary": PRIMARY,
        "secondary": SECONDARY,
        "accent": ACCENT,
        "positive": POSITIVE,
        "negative": NEGATIVE,
        "warning": WARNING,
        "info": INFO,
        "dark": DARK_SURFACE,
        "dark_page": DARK_PAGE,
    }
