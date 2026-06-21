#!/usr/bin/env bash
set -euo pipefail

# verify-full.sh — full verification suite
# Run before claiming Succeeded. May take several minutes.
# Replace the echo stubs below with real checks for this loop.

WORKSPACE="${1:-$(pwd)}"

echo "[verify-full] workspace: $WORKSPACE"

# --- GATE 1: fast gate must pass first ---
bash "$(dirname "$0")/verify-fast.sh" "$WORKSPACE"

# --- GATE 2: integration / e2e tests ---
# e.g. uv run pytest tests/ -q --tb=short
echo "[verify-full] STUB: integration tests — replace with real command"

# --- GATE 3: coverage threshold ---
# e.g. uv run pytest --cov=src --cov-fail-under=80
echo "[verify-full] STUB: coverage threshold — replace with real command"

# --- GATE 4: artifact quality check ---
# e.g. python3 scripts/judge-rubric.py --artifacts artifacts/ --rubric EVALS/rubrics/main.md
echo "[verify-full] STUB: artifact quality — replace with real command"

# --- GATE 5: security / secret scan ---
# e.g. grep -rE '(api_key|password|secret)\s*=' src/ && exit 1 || true
echo "[verify-full] STUB: secret scan — replace with real command"

# --- GATE 6: regression suite ---
# e.g. python3 scripts/extract-trace-metrics.py EVALS/traces/ | python3 scripts/verify-safety.py
echo "[verify-full] STUB: regression suite — replace with real command"

echo "[verify-full] PASS — all gates green"
exit 0
