#!/usr/bin/env bash
# Clears stale caches and restarts the Streamlit server.
# Run this after any code change to routeiq/ to force fresh instances.

set -euo pipefail

echo "Killing any running Streamlit process..."
pkill -f "streamlit run" 2>/dev/null && echo "  killed" || echo "  none running"

echo "Clearing OSMnx HTTP cache..."
rm -rf ~/.cache/osmnx/ && echo "  cleared"

echo "Clearing local app cache..."
rm -rf cache/ && echo "  cleared"

echo "Starting Streamlit..."
ANTHROPIC_API_KEY=$(grep -i anthropic /Users/ayyaswamy/projects/vibe-coding-app/.streamlit/secrets.toml | cut -d'"' -f2) \
  streamlit run app.py
