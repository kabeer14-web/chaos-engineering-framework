#!/usr/bin/env bash
# Switch the application between the weak baseline (v1) and the hardened design (v2).
# Usage: switch-version.sh v1|v2
source "$(dirname "$0")/lib.sh"
need kubectl
cd "$ROOT"
case "${1:-}" in
  v1)
    kubectl delete -f k8s/app/40-v2-hardened.yaml --ignore-not-found
    kubectl apply -f k8s/app/30-v1-weak.yaml ;;
  v2)
    kubectl delete -f k8s/app/30-v1-weak.yaml --ignore-not-found
    kubectl apply -f k8s/app/40-v2-hardened.yaml ;;
  *) die "usage: switch-version.sh v1|v2" ;;
esac
wait_rollout app backend
wait_rollout app frontend
log "now running $(current_version); waiting 30s for steady state"
sleep 30
kubectl -n app get pods -o wide
