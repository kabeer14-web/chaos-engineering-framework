#!/usr/bin/env bash
# Shared helpers. Source this file; do not run it.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CLUSTER="${CLUSTER:-chaos-lab}"
PROM_LOCAL="http://localhost:9090"

log()  { printf '\033[1;36m[%s]\033[0m %s\n' "$(date +%H:%M:%S)" "$*"; }
warn() { printf '\033[1;33m[warn]\033[0m %s\n' "$*" >&2; }
die()  { printf '\033[1;31m[error]\033[0m %s\n' "$*" >&2; exit 1; }

need() { for c in "$@"; do command -v "$c" >/dev/null 2>&1 || die "'$c' is not installed"; done; }

# Start a background port-forward to Prometheus (idempotent). Needed by the analyzer when run on the host.
prom_forward() {
  if curl -fsS "$PROM_LOCAL/-/ready" >/dev/null 2>&1; then return 0; fi
  log "port-forward Prometheus -> localhost:9090"
  nohup kubectl -n monitoring port-forward svc/kps-prometheus 9090:9090 >/tmp/pf-prom.log 2>&1 &
  for _ in $(seq 1 30); do
    curl -fsS "$PROM_LOCAL/-/ready" >/dev/null 2>&1 && return 0
    sleep 1
  done
  die "Prometheus not reachable on localhost:9090 (see /tmp/pf-prom.log)"
}

# Which app version is deployed right now (v1 | v2) - derived from the backend replica count label.
current_version() {
  kubectl -n app get deploy backend -o jsonpath='{.metadata.labels.lab\.version}' 2>/dev/null || echo unknown
}

wait_rollout() { kubectl -n "$1" rollout status "deploy/$2" --timeout="${3:-300s}"; }
