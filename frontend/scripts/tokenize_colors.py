"""Replace hard-coded CSS colours with semantic theme tokens (one-off migration; kept for reference).

Each hex colour is classified by hue, saturation and lightness into a token: a neutral ramp from
``--surface`` (paper) to ``--ink`` (text), the ``--accent`` family, ``--danger``, ``--success``, or a
translucent ``--shadow``. The light theme keeps the most frequent original colour of each token, so
the default look is nearly unchanged while every colour becomes themeable.
"""

import colorsys
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

HEX = re.compile(r"#(?:[0-9a-fA-F]{8}|[0-9a-fA-F]{6}|[0-9a-fA-F]{4}|[0-9a-fA-F]{3})\b")
NEUTRAL = [  # (upper lightness bound, token)
    (0.25, "ink"), (0.40, "ink-soft"), (0.55, "ink-muted"), (0.66, "ink-faint"), (0.78, "line-strong"),
    (0.875, "line"), (0.925, "surface-3"), (0.965, "surface-2"), (1.01, "surface"),
]
ACCENT = [(0.40, "accent-strong"), (0.62, "accent"), (0.84, "accent-soft"), (1.01, "accent-wash")]


def rgba(value: str) -> tuple[float, float, float, float]:
    """Parse a hex colour into 0-1 channels."""
    digits = value[1:]
    if len(digits) in (3, 4):
        digits = "".join(ch * 2 for ch in digits)
    channels = [int(digits[i : i + 2], 16) / 255 for i in range(0, len(digits), 2)]
    return (*channels[:3], channels[3] if len(channels) == 4 else 1.0)  # type: ignore[return-value]


def classify(value: str) -> tuple[str, float]:
    """Return a colour's token and its alpha."""
    r, g, b, a = rgba(value)
    hue, lightness, saturation = colorsys.rgb_to_hls(r, g, b)
    degrees = hue * 360
    if a < 1:
        return "shadow", a
    near_white = lightness > 0.9 and saturation < 0.6  # warm paper tones, not accents
    if saturation > 0.33 and 0.12 < lightness < 0.97 and not near_white:
        if degrees < 16 or degrees > 340:
            return ("danger" if lightness < 0.7 else "danger-soft"), a
        if 80 < degrees < 170:
            return ("success" if lightness < 0.7 else "success-soft"), a
        if 16 <= degrees <= 60:
            return next(token for bound, token in ACCENT if lightness < bound), a
    if 80 < degrees < 170 and saturation > 0.12 and lightness < 0.9:
        return ("success" if lightness < 0.7 else "success-soft"), a
    return next(token for bound, token in NEUTRAL if lightness < bound), a


def main(files: list[Path]) -> None:
    """Rewrite each CSS file and print the light-theme value chosen for every token."""
    seen: dict[str, Counter[str]] = defaultdict(Counter)
    for path in files:
        text = path.read_text()

        def replace(match: re.Match[str]) -> str:
            """Swap one colour for its token."""
            value = match.group(0).lower()
            token, alpha = classify(value)
            if token == "shadow":
                return f"color-mix(in srgb, var(--shadow) {round(alpha * 100)}%, transparent)"
            seen[token][value] += 1
            return f"var(--{token})"

        path.write_text(HEX.sub(replace, text))
    for token, counts in sorted(seen.items()):
        print(f"  --{token}: {counts.most_common(1)[0][0]};  /* {sum(counts.values())} uses, {len(counts)} originals */")


if __name__ == "__main__":
    main([Path(arg) for arg in sys.argv[1:]])
