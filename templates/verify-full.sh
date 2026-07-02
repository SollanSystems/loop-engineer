#!/usr/bin/env bash
set -euo pipefail

# verify-full — full verification suite. Run before claiming Succeeded.
# Composes the fast gate, then this loop's deeper checks. Add integration/e2e,
# coverage, artifact-quality, secret-scan, and regression gates as the SPEC
# criteria earn them — [[loop-evals]] owns the proof surface.

WORKSPACE="${1:-$(pwd)}"

echo "[verify-full] workspace: $WORKSPACE"

# --- GATE 1: fast gate must pass first ---
fast="$(dirname "$0")/verify-fast"
[ -x "$fast" ] || fast="$(dirname "$0")/verify-fast.sh"
bash "$fast" "$WORKSPACE"

# --- GATE 2: integration / e2e tests ---
# e.g. uv run pytest tests/ -q --tb=short

# --- GATE 3: coverage threshold ---
# e.g. uv run pytest --cov=src --cov-fail-under=80

# --- GATE 4: artifact quality check (advisory — never blocks) ---
# e.g. bash scripts/judge-rubric "$WORKSPACE" EVALS/rubrics/main.md

# --- GATE 5: secret scan ---
# e.g. grep -rE '(api_key|password|secret)\s*=' src/ && exit 1 || true

# --- GATE 6: regression + safety suite ---
# e.g. bash scripts/extract-trace-metrics "$WORKSPACE" && bash scripts/verify-safety "$WORKSPACE"

echo "[verify-full] PASS — all gates green"
exit 0
