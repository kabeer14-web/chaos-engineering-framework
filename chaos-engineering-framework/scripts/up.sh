#!/usr/bin/env bash
# Build the whole lab from zero: cluster -> observability -> chaos engine -> workflow engine -> app (v1).
# Safe to re-run: every step is idempotent. Takes ~10-15 minutes the first time.
source "$(dirname "$0")/lib.sh"
need docker kind kubectl helm
cd "$ROOT"

KPS_VERSION="${KPS_VERSION:-61.3.2}"
CHAOS_MESH_VERSION="${CHAOS_MESH_VERSION:-2.6.3}"
ARGO_VERSION="${ARGO_VERSION:-v3.5.8}"
METRICS_SERVER_VERSION="${METRICS_SERVER_VERSION:-v0.7.1}"

# ---------------------------------------------------------------- 1. cluster
if kind get clusters 2>/dev/null | grep -qx "$CLUSTER"; then
  log "cluster '$CLUSTER' already exists"
else
  log "creating kind cluster (1 control-plane + 3 workers)"
  kind create cluster --name "$CLUSTER" --config kind/kind-config.yaml --wait 120s
fi
kubectl config use-context "kind-$CLUSTER" >/dev/null

# Worker roles: first worker = infra (monitoring/tools), the other two = app (nodes we are allowed to kill).
mapfile -t WORKERS < <(kubectl get nodes -l '!node-role.kubernetes.io/control-plane' -o name | sort)
kubectl label --overwrite "${WORKERS[0]}" lab.role=infra
kubectl label --overwrite "${WORKERS[1]}" "${WORKERS[2]}" lab.role=app
kubectl get nodes -L lab.role

kubectl apply -f k8s/00-namespaces.yaml

# ---------------------------------------------------------------- 2. metrics-server (needed by the HPA in v2)
log "metrics-server"
kubectl apply -f "https://github.com/kubernetes-sigs/metrics-server/releases/download/${METRICS_SERVER_VERSION}/components.yaml"
kubectl -n kube-system patch deploy metrics-server --type=json \
  -p '[{"op":"add","path":"/spec/template/spec/containers/0/args/-","value":"--kubelet-insecure-tls"}]' || true

# ---------------------------------------------------------------- 3. observability
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts >/dev/null
helm repo add grafana https://grafana.github.io/helm-charts >/dev/null
helm repo add chaos-mesh https://charts.chaos-mesh.org >/dev/null
helm repo update >/dev/null

log "Prometheus + Grafana (kube-prometheus-stack $KPS_VERSION)"
helm upgrade --install kps prometheus-community/kube-prometheus-stack -n monitoring \
  --version "$KPS_VERSION" -f k8s/observability/kube-prometheus-stack-values.yaml --wait --timeout 10m

log "Loki + Promtail (logs)"
helm upgrade --install loki grafana/loki-stack -n logging --version 2.10.2 \
  -f k8s/observability/loki-stack-values.yaml --wait --timeout 5m

log "Jaeger (traces) + OpenTelemetry Collector"
kubectl apply -f k8s/observability/jaeger.yaml -f k8s/observability/otel-collector.yaml
wait_rollout observability jaeger
wait_rollout observability otel-collector

log "Grafana dashboard"
kubectl -n monitoring create configmap chaos-lab-dashboard \
  --from-file=k8s/observability/dashboards/chaos-lab.json --dry-run=client -o yaml \
  | kubectl label --local -f - grafana_dashboard=1 -o yaml | kubectl apply -f -

# ---------------------------------------------------------------- 4. chaos engine
log "Chaos Mesh $CHAOS_MESH_VERSION"
kubectl create ns chaos-mesh --dry-run=client -o yaml | kubectl apply -f -
helm upgrade --install chaos-mesh chaos-mesh/chaos-mesh -n chaos-mesh --version "$CHAOS_MESH_VERSION" \
  -f k8s/observability/chaos-mesh-values.yaml --wait --timeout 5m

# ---------------------------------------------------------------- 5. workflow engine (Argo)
log "Argo Workflows $ARGO_VERSION"
kubectl apply -n argo -f "https://github.com/argoproj/argo-workflows/releases/download/${ARGO_VERSION}/install.yaml"
for d in workflow-controller argo-server; do
  kubectl -n argo patch deploy "$d" --type=merge -p '{"spec":{"template":{"spec":{"nodeSelector":{"lab.role":"infra"}}}}}'
done
kubectl -n argo patch deploy argo-server --type=json \
  -p '[{"op":"add","path":"/spec/template/spec/containers/0/args","value":["server","--auth-mode=server"]}]'
wait_rollout argo workflow-controller
wait_rollout argo argo-server
kubectl apply -f k8s/argo/rbac.yaml -f k8s/argo/chaos-workflow.yaml
kubectl -n argo create configmap chaos-experiments --from-file=k8s/chaos --dry-run=client -o yaml | kubectl apply -f -

# ---------------------------------------------------------------- 6. application (v1 = weak baseline)
"$ROOT/scripts/build-images.sh"
kubectl apply -f k8s/app/10-services-monitoring.yaml -f k8s/app/20-loadgen.yaml -f k8s/app/30-v1-weak.yaml
wait_rollout app backend
wait_rollout app frontend
wait_rollout app loadgen

log "DONE. App version: $(current_version)."
log "Next:  make forward   (UIs on localhost)   |   make experiment EXP=pod-kill"
