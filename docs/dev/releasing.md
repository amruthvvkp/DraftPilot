# Releasing

A release publishes four things from one tag: the `draftpilot-studio` and `draftpilot-mcp` wheels on
PyPI, the `ghcr.io/amruthvvkp/draftpilot` image (amd64 and arm64), and a GitHub Release with the
wheels, sdists and Compose files.

## Layout

- The repository is a uv workspace. The root project is **`draftpilot-studio`** (module
  `draftpilot`, command `draftpilot`; the PyPI name `draftpilot` belongs to another project).
  `packages/draftpilot-mcp` is a member that depends on it at the same version.
- The wheel carries the role specs, the Alembic migrations (`src/draftpilot/migrations`) and the
  studio build. `scripts/build_release.sh` builds the studio and copies it into
  `src/draftpilot/studio/` (git-ignored) before `uv build --all-packages`.
- The `Dockerfile` builds the same wheels and installs them into the `runtime` target. Its `dev`
  target installs the source tree editable for `compose.dev.yml`.

## Cut a release

1. Set the same version in `pyproject.toml`, `packages/draftpilot-mcp/pyproject.toml`, and the
   `draftpilot-studio==<version>` dependency of `draftpilot-mcp`; run `uv lock`.
2. Run `scripts/build_release.sh` locally and install `dist/*.whl` in a clean environment
   (`uv venv /tmp/smoke && VIRTUAL_ENV=/tmp/smoke uv pip install dist/*.whl`).
3. Commit, then tag and push: `git tag v0.2.0 && git push origin v0.2.0`.

`.github/workflows/release.yml` checks that the tag matches both versions, builds and smoke-tests the
wheels, publishes to PyPI with trusted publishing, pushes the image, then creates the GitHub Release.

## One-time setup

- **PyPI:** add a trusted publisher for both `draftpilot-studio` and `draftpilot-mcp` (repository
  `amruthvvkp/DraftPilot`, workflow `release.yml`, environment `pypi`), and create the `pypi`
  environment in the repository settings.
- **GHCR:** nothing to configure; the workflow uses `GITHUB_TOKEN` with `packages: write`. Make the
  package public in its settings after the first push.
- **Docs:** enable GitHub Pages with *GitHub Actions* as the source; `docs.yml` deploys on `main`.
