"""Keep generated documentation in step with the code."""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parents[1]


def test_http_api_reference_is_current() -> None:
    """docs/dev/http-api.md matches the app's OpenAPI schema (regenerate with scripts/gen_http_api_docs.py)."""
    result = subprocess.run([sys.executable, "scripts/gen_http_api_docs.py", "--check"], cwd=ROOT, capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr or result.stdout


def test_every_docs_page_is_in_the_nav() -> None:
    """No page is orphaned: every Markdown file under docs/ appears in zensical.toml's nav."""
    nav = (ROOT / "zensical.toml").read_text()
    pages = [path.relative_to(ROOT / "docs").as_posix() for path in (ROOT / "docs").rglob("*.md") if "superpowers" not in path.parts]
    assert [page for page in pages if f'"{page}"' not in nav] == []
