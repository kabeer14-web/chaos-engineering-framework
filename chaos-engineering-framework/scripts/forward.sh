#!/usr/bin/env bash
# Expose the UIs on localhost (in Codespaces the Ports tab shows them as clickable links).
#   Grafana 3000 (admin/admin) | Prometheus 9090 | Jaeger 16686 | Argo 2746 | frontend 8080
source "$(dirname "$0")/lib.sh"
need kubectl
pkill -f "kubectl.*port-forward" 2>/dev/null || true
sleep 1
pf() { nohup kubectl -n "$1" port-forward "svc/$2" "$3" >"/tmp/pf-$2.log" 2>&1 & }
pf monitoring kps-grafana 3000:80
pf monitoring kps-prometheus 9090:9090
pf observability jaeger 16686:16686
pf argo argo-server 2746:2746
pf app frontend 8080:8080
sleep 3
cat <<MSG
Grafana     http://localhost:3000   (admin / admin)  -> dashboard "Chaos Lab - Resilience"
Prometheus  http://localhost:9090
Jaeger      http://localhost:16686
Argo        https://localhost:2746  (self-signed certificate: accept the warning)
Frontend    http://localhost:8080
MSG
