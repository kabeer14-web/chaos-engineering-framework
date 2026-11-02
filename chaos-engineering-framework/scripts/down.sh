#!/usr/bin/env bash
# Delete the whole cluster (frees all CPU/RAM/disk). Your repo and results/ stay.
source "$(dirname "$0")/lib.sh"
need kind
pkill -f "kubectl.*port-forward" 2>/dev/null || true
kind delete cluster --name "$CLUSTER"
