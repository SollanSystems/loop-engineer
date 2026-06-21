#!/usr/bin/env bash
set -euo pipefail

# verify-fast.sh — quick deterministic gate
# Run after every task iteration. Must complete in <30s.
# Replace the echo stubs below with real checks for this loop.

WORKSPACE="${1:-$(pwd)}"

echo "[verify-fast] workspace: $WORKSPACE"

# --- CHECK: lint / typecheck ---
# e.g. cd "$WORKSPACE" && npm run typecheck
echo "[verify-fast] STUB: lint/typecheck — replace with real command"

# --- CHECK: unit tests (fast subset) ---
# e.g. uv run pytest tests/unit/ -q --tb=short
echo "[verify-fast] STUB: unit tests — replace with real command"

# --- CHECK: schema / contract validation ---
# e.g. python3 scripts/validate_frontmatter.py
echo "[verify-fast] STUB: schema validation — replace with real command"

echo "[verify-fast] PASS"
exit 0
