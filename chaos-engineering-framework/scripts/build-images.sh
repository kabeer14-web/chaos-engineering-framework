#!/usr/bin/env bash
# Build the 4 images and load them straight into the kind nodes (no registry needed).
source "$(dirname "$0")/lib.sh"
need docker kind
cd "$ROOT"
for svc in frontend backend loadgen; do
  log "building chaos-lab/$svc:1.0"
  docker build -q -t "chaos-lab/$svc:1.0" -f "app/$svc/Dockerfile" app
done
log "building chaos-lab/aiops:1.0"
docker build -q -t chaos-lab/aiops:1.0 aiops
for img in frontend backend loadgen aiops; do
  kind load docker-image "chaos-lab/$img:1.0" --name "$CLUSTER"
done
log "images loaded into cluster '$CLUSTER'"
