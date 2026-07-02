#!/usr/bin/env bash
set -euo pipefail

# verify-fast — quick deterministic gate. Run after every task; keep it under ~30s.
# Ships with one real, dependency-free check: the operating contract's own files
# are present. Extend it with this loop's fast checks (lint, typecheck, unit
# subset) as the SPEC criteria earn them — [[loop-evals]] owns the proof surface.

WORKSPACE="${1:-$(pwd)}"

echo "[verify-fast] workspace: $WORKSPACE"

for f in SPEC.md WORKFLOW.md TASKS.json .loop/state.json; do
  if [ ! -f "$WORKSPACE/$f" ]; then
    echo "[verify-fast] FAIL: contract file missing: $f"
    exit 1
  fi
done

# --- CHECK: lint / typecheck ---
# e.g. (cd "$WORKSPACE" && npm run typecheck)

# --- CHECK: unit tests (fast subset) ---
# e.g. uv run pytest tests/unit/ -q --tb=short

echo "[verify-fast] PASS"
exit 0
