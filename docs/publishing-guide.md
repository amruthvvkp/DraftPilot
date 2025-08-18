# UV Workspace Build and Packaging Guide for DraftPilot

## Project Structure

Your workspace has the root as both the workspace root AND the main UI package:

```
draftpilot/                    # Root (workspace + UI package)
├── src/
│   └── draftpilot/           # UI package source
│       ├── __init__.py
│       ├── main.py
│       ├── components.py
│       └── api_routes.py
├── packages/
│   ├── core/                 # Core package (shared, not published)
│   │   ├── src/
│   │   │   └── draftpilot_core/
│   │   │       ├── __init__.py
│   │   │       ├── models.py
│   │   │       ├── parser.py
│   │   │       ├── formatter.py
│   │   │       ├── ai.py
│   │   │       └── config.py
│   │   ├── pyproject.toml
│   │   └── README.md
│   └── draftpilot-mcp/       # MCP server package
│       ├── src/
│       │   └── draftpilot_mcp/
│       │       ├── __init__.py
│       │       └── server.py
│       ├── pyproject.toml
│       └── README.md
├── pyproject.toml            # Root config (workspace + UI)
├── uv.lock                   # Single lockfile for all packages
├── .python-version           # Python version for the project
├── .gitignore
└── README.md
```

## Key Concepts

### Workspace Architecture
- **Root is dual-purpose**: Acts as both workspace root AND the main UI package
- **Single lockfile**: All packages share `uv.lock` for consistent dependencies
- **Workspace members**: Packages in `packages/*` are workspace members
- **Core is private**: `draftpilot-core` is bundled into other packages, not published separately

### How Dependencies Work
1. **During Development**: 
   - All packages installed in editable mode
   - Changes to core immediately reflected in UI and MCP
   - Single virtual environment (`.venv`) at root

2. **During Build**:
   - `uv_build` backend handles workspace dependencies
   - Core package source is bundled into each dependent package
   - Result: Self-contained wheels with core included

## Initial Setup

### 1. Install UV

```bash
# macOS/Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"

# Verify installation
uv --version
```

### 2. Clone and Initialize

```bash
# Clone repository
git clone https://github.com/yourusername/draftpilot.git
cd draftpilot

# Create Python environment and sync dependencies
uv sync

# This will:
# - Create .venv at root
# - Install all workspace packages in editable mode
# - Install all dependencies from uv.lock
```

### 3. Verify Installation

```bash
# Check that all packages are installed
uv pip list | grep draftpilot

# Should show:
# draftpilot         0.1.0    /path/to/draftpilot
# draftpilot-core    0.1.0    /path/to/draftpilot/packages/core
# draftpilot-mcp     0.1.0    /path/to/draftpilot/packages/draftpilot-mcp
```

## Development Workflow

### Running Applications

```bash
# Run the UI application (from root)
uv run python -m draftpilot.main

# Or using the script entry point
uv run draftpilot

# Run the MCP server
uv run --package draftpilot-mcp draftpilot-mcp

# Or run it directly
uv run --package draftpilot-mcp uvicorn draftpilot_mcp.server:app --reload

# Run with specific Python version
uv run --python 3.12 python -m draftpilot.main
```

### Managing Dependencies

```bash
# Add dependency to root (UI) package
uv add requests
uv add --dev pytest-cov  # Dev dependency

# Add to specific workspace member
uv add --package draftpilot-mcp redis
uv add --package draftpilot-core pyyaml

# Update all dependencies
uv lock --upgrade

# Update specific dependency
uv lock --upgrade-package flet

# Sync after manual pyproject.toml changes
uv sync
```

### Working with Packages

```bash
# Sync all workspace packages
uv sync --all-packages

# Sync specific package only
uv sync --package draftpilot-mcp

# Sync without installing workspace members (only deps)
uv sync --no-install-workspace

# Sync frozen (exact versions from lock)
uv sync --frozen
```

## Building Packages

### Build Commands

```bash
# Build the root UI package (includes draftpilot-core)
uv build

# Output:
# - dist/draftpilot-0.1.0-py3-none-any.whl
# - dist/draftpilot-0.1.0.tar.gz

# Build the MCP package (includes draftpilot-core)
uv build packages/draftpilot-mcp
# Or
uv build --package draftpilot-mcp

# Build all packages
uv build && uv build packages/draftpilot-mcp
```

### Build for Publishing (PyPI)

```bash
# Build without workspace sources (tests PyPI compatibility)
uv build --no-sources
uv build --no-sources packages/draftpilot-mcp

# These builds ensure packages work without workspace context
```

### Understanding Build Output

When you build with `uv_build`:

1. **Workspace resolution**: UV identifies `draftpilot-core = { workspace = true }`
2. **Source bundling**: Core package source is copied into the wheel
3. **Dependency merging**: Core's dependencies added to package metadata
4. **Self-contained result**: Each wheel works independently

Example wheel contents:
```
draftpilot-0.1.0-py3-none-any.whl/
├── draftpilot/
│   ├── __init__.py
│   ├── main.py
│   └── components.py
├── draftpilot_core/           # Core bundled here!
│   ├── __init__.py
│   ├── models.py
│   └── parser.py
└── draftpilot-0.1.0.dist-info/
    └── METADATA               # Includes core's dependencies
```

## Platform-Specific Builds

### Flet Desktop Application

```bash
# Build Python package first
uv build

# Create desktop executable with Flet
uv run flet pack src/draftpilot/main.py \
  --name DraftPilot \
  --product-name "DraftPilot" \
  --product-version "0.1.0" \
  --copyright "Copyright (c) 2024" \
  --icon assets/icon.png

# Platform-specific builds
uv run flet pack src/draftpilot/main.py --target windows
uv run flet pack src/draftpilot/main.py --target macos
uv run flet pack src/draftpilot/main.py --target linux
```

### Export Dependencies by Platform

```bash
# Export for different platforms
uv export --platform windows --python-version 3.12 > requirements-windows.txt
uv export --platform linux --python-version 3.12 > requirements-linux.txt
uv export --platform macos-arm64 --python-version 3.12 > requirements-macos.txt

# Export without dev dependencies
uv export --no-dev > requirements-prod.txt
```

## Docker Deployment

### Multi-stage Dockerfile

```dockerfile
# Build stage
FROM python:3.12-slim as builder

WORKDIR /app

# Install UV
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy workspace files
COPY pyproject.toml uv.lock ./
COPY packages/ ./packages/
COPY src/ ./src/

# Build the MCP package
RUN uv build --package draftpilot-mcp

# Runtime stage
FROM python:3.12-slim

WORKDIR /app

# Copy and install the built wheel
COPY --from=builder /app/packages/draftpilot-mcp/dist/*.whl ./
RUN pip install --no-cache-dir draftpilot_mcp-*.whl

EXPOSE 8551

CMD ["draftpilot-mcp"]
```

### Docker Compose for Development

```yaml
version: '3.8'

services:
  ui:
    build:
      context: .
      dockerfile: Dockerfile.ui
    ports:
      - "8550:8550"
    volumes:
      - ./src:/app/src
      - ./packages/core:/app/packages/core
    environment:
      - OPENAI_API_KEY=${OPENAI_API_KEY}
    command: uv run draftpilot

  mcp:
    build:
      context: .
      dockerfile: Dockerfile.mcp
    ports:
      - "8551:8551"
    volumes:
      - ./packages/draftpilot-mcp:/app/packages/draftpilot-mcp
      - ./packages/core:/app/packages/core
    command: uv run --package draftpilot-mcp uvicorn draftpilot_mcp.server:app --reload --host 0.0.0.0
```

## Testing and Validation

### Test Built Packages

```bash
# Create isolated test environment
uv venv test-env
source test-env/bin/activate  # Windows: test-env\Scripts\activate

# Install and test UI package
uv pip install dist/draftpilot-0.1.0-py3-none-any.whl
python -c "from draftpilot_core import Screenplay; print('✓ Core bundled')"
python -c "from draftpilot import main; print('✓ UI works')"
draftpilot --version

# Test MCP package
uv pip install packages/draftpilot-mcp/dist/draftpilot_mcp-0.1.0-py3-none-any.whl
python -c "from draftpilot_mcp import server; print('✓ MCP works')"
draftpilot-mcp --help

deactivate
```

### Verify Package Contents

```bash
# List wheel contents
unzip -l dist/draftpilot-0.1.0-py3-none-any.whl | grep draftpilot_core

# Extract and examine metadata
unzip -p dist/draftpilot-0.1.0-py3-none-any.whl draftpilot-0.1.0.dist-info/METADATA

# Check that core dependencies are included
unzip -p dist/draftpilot-0.1.0-py3-none-any.whl draftpilot-0.1.0.dist-info/METADATA | grep pydantic
```

### Run Tests

```bash
# Run tests for all packages
uv run pytest

# Run tests for specific package
uv run --package draftpilot-core pytest packages/core/tests
uv run --package draftpilot-mcp pytest packages/draftpilot-mcp/tests

# Run with coverage
uv run pytest --cov=draftpilot --cov=draftpilot_core --cov=draftpilot_mcp
```

## Publishing to PyPI

### Pre-publish Checklist

- [ ] Version numbers updated in all `pyproject.toml` files
- [ ] `uv.lock` is up to date (`uv lock`)
- [ ] Tests pass (`uv run pytest`)
- [ ] Build without sources works (`uv build --no-sources`)
- [ ] Test installation in clean environment
- [ ] README and documentation updated

### Publishing Process

```bash
# 1. Build packages for distribution
uv build --no-sources
uv build --no-sources packages/draftpilot-mcp

# 2. Test with TestPyPI first (optional)
uv publish --index testpypi dist/draftpilot-0.1.0-py3-none-any.whl

# 3. Publish to PyPI
uv publish dist/draftpilot-0.1.0-py3-none-any.whl
uv publish packages/draftpilot-mcp/dist/draftpilot_mcp-0.1.0-py3-none-any.whl

# Or publish with token
export UV_PUBLISH_TOKEN=your-pypi-token
uv publish dist/*.whl
```

## CI/CD Integration

### GitHub Actions Example

```yaml
name: Build and Test

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      
      - name: Install UV
        uses: astral-sh/setup-uv@v4
        
      - name: Set up Python
        run: uv python install 3.12
        
      - name: Install dependencies
        run: uv sync --frozen
        
      - name: Run tests
        run: uv run pytest
        
      - name: Build packages
        run: |
          uv build
          uv build --package draftpilot-mcp
          
      - name: Upload artifacts
        uses: actions/upload-artifact@v4
        with:
          name: dist
          path: |
            dist/
            packages/draftpilot-mcp/dist/
```

## Troubleshooting

### Common Issues and Solutions

#### Issue: "draftpilot-core not found"
```bash
# Solution: Ensure workspace member is properly configured
# Check pyproject.toml has:
[tool.uv.sources]
draftpilot-core = { workspace = true }

# Re-sync workspace
uv sync --reinstall
```

#### Issue: "Module not found after build"
```bash
# Solution: Check package structure
ls -la packages/core/src/  # Should have draftpilot_core/
ls -la src/  # Should have draftpilot/

# Ensure __init__.py files exist
find . -type d -name "draftpilot*" -exec ls -la {} \;
```

#### Issue: "Build fails with uv_build"
```bash
# Solution: Check UV version
uv --version  # Should be >= 0.8.11

# Update UV
uv self update

# Clear cache and rebuild
rm -rf dist/
uv cache clean
uv build
```

#### Issue: "Dependencies not included in wheel"
```bash
# Solution: Verify build-system in all packages
grep -r "build-backend" packages/*/pyproject.toml

# Should show:
# build-backend = "uv_build"
```

## Best Practices

1. **Version Management**
   - Keep all package versions synchronized
   - Use semantic versioning
   - Update versions before building for release

2. **Dependency Management**
   - Pin critical dependencies in production
   - Use `uv lock --upgrade` regularly in development
   - Test with `--no-sources` before publishing

3. **Development Workflow**
   - Always work in virtual environment
   - Use `uv sync --frozen` in CI/CD
   - Keep `uv.lock` in version control

4. **Building and Publishing**
   - Test builds in clean environments
   - Use TestPyPI before production PyPI
   - Document build requirements clearly

5. **Workspace Organization**
   - Keep core functionality in `draftpilot-core`
   - Maintain clear boundaries between packages
   - Use workspace for shared development, not conflicting requirements

## Summary

This workspace setup provides:
- ✅ Single development environment for all packages
- ✅ Automatic bundling of core into published packages
- ✅ Consistent dependency versions via unified lockfile
- ✅ Clean separation between UI and MCP server
- ✅ Private core package (not published separately)
- ✅ Native UV build system with `uv_build` backend

The key is the root `pyproject.toml` serving dual purpose as workspace root and UI package, with proper `[tool.uv.sources]` configuration to reference workspace members.
