#!/bin/bash
# Test runner script for DraftPilot

set -e

echo "=== Running DraftPilot Tests ==="
echo ""

echo "1. Testing imports..."
uv run python test_imports.py
echo ""

echo "2. Running unit tests..."
uv run pytest tests/unit/ -v --tb=short
echo ""

echo "✓ All tests completed!"

