#!/usr/bin/env bash
# Build the release artifacts: the studio, then the draftpilot and draftpilot-mcp wheels and sdists.
#
#   scripts/build_release.sh          # → dist/*.whl, dist/*.tar.gz (the studio is inside the draftpilot wheel)
set -euo pipefail
cd "$(dirname "$0")/.."

npm --prefix frontend ci
npm --prefix frontend run build
rm -rf src/draftpilot/studio
cp -R frontend/dist src/draftpilot/studio

rm -rf dist
uv build --all-packages --out-dir dist
uvx twine check --strict dist/*
ls -1 dist
