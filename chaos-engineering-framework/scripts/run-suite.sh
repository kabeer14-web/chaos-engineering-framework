#!/usr/bin/env bash
# The complete before/after study. For each app version (v1 weak, v2 hardened) run all four experiments,
# then build the comparison table. ~45 minutes. Results go to results/.
# Usage: run-suite.sh            (both versions)    |    run-suite.sh v2   (only one)
source "$(dirname "$0")/lib.sh"
cd "$ROOT"
VERSIONS=("$@")
[ ${#VERSIONS[@]} -eq 0 ] && VERSIONS=(v1 v2)
for V in "${VERSIONS[@]}"; do
  log "=============== app version $V ==============="
  "$ROOT/scripts/switch-version.sh" "$V"
  for EXP in pod-kill network-delay cpu-stress; do
    log "--- $V / $EXP ---"
    "$ROOT/scripts/run-argo.sh" "$EXP" "$V"
    # return to the reference state (AI remediation may have scaled things) before the next experiment
    "$ROOT/scripts/switch-version.sh" "$V" >/dev/null
  done
  log "--- $V / node-failure ---"
  "$ROOT/scripts/run-node-failure.sh" "$V"
  "$ROOT/scripts/switch-version.sh" "$V" >/dev/null
done
python3 "$ROOT/aiops/compare.py"
