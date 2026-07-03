#!/usr/bin/env bash
set -euo pipefail

# extract-trace-metrics — turn the loop's run history into the loop-behavior +
# cost metrics (eval Layers 4 and 7). Reads the externalized trace surface
# (RUNLOG.md, EVALS/traces/, .loop/receipts/*.jsonl) and emits a metrics JSON —
# the derived inputs behind false-completion-rate and repair-productivity, never
# a self-reported claim. [[loop-evals]] defines the formulas; [[loop-flywheel]]
# watches the trend. This stub emits an honest empty skeleton until real traces
# accumulate.

WORKSPACE="${1:-$(pwd)}"

RECEIPTS_DIR="$WORKSPACE/.loop/receipts"
receipts=0
if [ -d "$RECEIPTS_DIR" ]; then
  receipts=$(find "$RECEIPTS_DIR" -name '*.jsonl' -type f | wc -l | tr -d ' ')
fi

# --- METRICS: derive from evidence, not narration ---
# Replace the nulls below by joining RUNLOG self-reports to the layer-1 verify
# bundle per iteration_id (FCR) and the repair records' before/after scores (RP).
# e.g. FCR = (claimed-success AND verify-failed) / (claimed-success)
#      RP  = (repair passes where after.score > before.score) / (repair passes)

printf '{"receipt_files": %s, "false_completion_rate": null, "repair_productivity": null, "cost_per_success": null}\n' "$receipts"
exit 0
