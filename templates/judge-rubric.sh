#!/usr/bin/env bash
set -euo pipefail

# judge-rubric — advisory rubric-judge harness (eval Layer 2). ADVISORY ONLY:
# it never blocks a run — a model verdict may ADD a finding but can never clear a
# red deterministic gate (verify-fast/verify-full remain authoritative). Run it
# only after the deterministic gate is green. [[loop-evals]] owns the real judge
# wiring and calibration (Layer 3); this stub prints an advisory verdict and
# always exits 0 so it can never gate the loop by accident.

WORKSPACE="${1:-$(pwd)}"
RUBRIC="${2:-$WORKSPACE/EVALS/rubrics/main.md}"

echo "[judge-rubric] workspace: $WORKSPACE"
echo "[judge-rubric] rubric: $RUBRIC"

if [ ! -f "$RUBRIC" ]; then
  echo "[judge-rubric] ADVISORY: no rubric at $RUBRIC yet — nothing to score (add EVALS/rubrics/)"
  exit 0
fi

# --- SCORE: dispatch the rubric judge (reason -> sonnet; see reference/model-routing.md) ---
# The judge is a grading COMPONENT invoked by this script, never the system of record.
# e.g. python3 scripts/judge_rubric.py --artifacts artifacts/ --rubric "$RUBRIC" --json
#      then compare the rubric mean to the advisory threshold and PRINT it.

echo "[judge-rubric] ADVISORY: wire the judge in [[loop-evals]] — this stub does not gate"
exit 0
