#!/bin/bash
# Run DraftPilot app locally

set -e

echo "=== Starting DraftPilot Application ==="
echo ""
echo "Note: Make sure Redis is running on localhost:6379"
echo "      Or set DRAFTPILOT_REDIS_URL environment variable"
echo ""
echo "Starting server on http://localhost:8000"
echo "Press Ctrl+C to stop"
echo ""

uv run uvicorn draftpilot.app.main:app --host 0.0.0.0 --port 8000 --reload

