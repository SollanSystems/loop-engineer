#!/usr/bin/env bash
set -euo pipefail

# verify-safety — safety / approval / injection gate. BLOCKING for any loop that
# takes side effects (destructive commands, secret access, production mutation,
# money movement). Runs before Succeeded on a high-risk loop; [[loop-evals]] owns
# the real red-team logic (Layer 5). Ships one real, dependency-free check: no
# secret-shaped literal leaked into the tracked contract. Extend it with this
# loop's approval-bypass tests, injection probes, and canary checks as the SPEC
# earns them.

WORKSPACE="${1:-$(pwd)}"

echo "[verify-safety] workspace: $WORKSPACE"

# --- CHECK: no assigned secret literals in tracked source ---
# Flags a label immediately assigned an inline value (env-var NAMES alone are fine).
# Tighten the value side to a quoted 8+ char token once this loop has real source.
if grep -rInE '(api[_-]?key|secret|passwd|password|token)[[:space:]]*=[[:space:]]*[^[:space:]]' \
     --exclude-dir=.git --exclude-dir=.loop "$WORKSPACE"/src 2>/dev/null; then
  echo "[verify-safety] FAIL: assigned secret literal found — move it to the environment"
  exit 1
fi

# --- CHECK: approval-bypass tests ---
# e.g. assert every side-effecting task in TASKS.json maps to an approval_gate.

# --- CHECK: prompt-injection probes ---
# e.g. run the injection-probe set in EVALS/dataset/ and assert 0 escapes.

# --- CHECK: verifier-gaming canaries ---
# e.g. assert the tracked verify-* / test files match their known-good hashes.

echo "[verify-safety] PASS"
exit 0
