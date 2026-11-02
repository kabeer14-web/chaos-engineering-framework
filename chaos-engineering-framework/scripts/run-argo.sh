#!/usr/bin/env bash
# Run ONE chaos experiment through Argo Workflows (baseline -> inject -> hold -> release -> settle
# -> AI analysis -> automatic remediation if the AI asks for it) and save the AI report in results/.
# Usage: run-argo.sh <pod-kill|network-delay|cpu-stress> [label]      (label defaults to the deployed version)
source "$(dirname "$0")/lib.sh"
need kubectl
cd "$ROOT"
EXP="${1:?usage: run-argo.sh <pod-kill|network-delay|cpu-stress> [label]}"
LABEL="${2:-$(current_version)}"
[ -f "k8s/chaos/$EXP.yaml" ] || die "unknown experiment '$EXP' (see k8s/chaos/)"

kubectl -n argo create configmap chaos-experiments --from-file=k8s/chaos --dry-run=client -o yaml | kubectl apply -f -
kubectl apply -f k8s/argo/chaos-workflow.yaml >/dev/null

WF=$(kubectl -n argo create -o jsonpath='{.metadata.name}' -f - <<YAML
apiVersion: argoproj.io/v1alpha1
kind: Workflow
metadata:
  generateName: chaos-${EXP}-
  namespace: argo
spec:
  workflowTemplateRef: {name: chaos-experiment}
  arguments:
    parameters:
      - {name: experiment, value: "${EXP}"}
      - {name: label, value: "${LABEL}"}
YAML
)
log "workflow $WF submitted (experiment=$EXP, app=$LABEL)"

# Poll until the workflow finishes (typically ~4-5 minutes).
while true; do
  PHASE=$(kubectl -n argo get wf "$WF" -o jsonpath='{.status.phase}' 2>/dev/null || true)
  PROGRESS=$(kubectl -n argo get wf "$WF" -o jsonpath='{.status.progress}' 2>/dev/null || true)
  printf '\r  phase=%-10s progress=%-6s' "${PHASE:-Pending}" "${PROGRESS:-?}"
  case "$PHASE" in Succeeded|Failed|Error) echo; break ;; esac
  sleep 5
done
[ "$PHASE" = "Succeeded" ] || { kubectl -n argo get wf "$WF" -o yaml | tail -40; die "workflow ended with phase $PHASE"; }

# Pull the AI report out of the analyze step's log.
POD=$(kubectl -n argo get pods -l "workflows.argoproj.io/workflow=$WF" -o name | grep analyze | head -1)
mkdir -p results
OUT="results/$(date +%Y%m%d-%H%M%S)_${LABEL}_${EXP}.json"
kubectl -n argo logs "$POD" -c main | sed -n '/===REPORT-BEGIN===/,/===REPORT-END===/p' | sed '1d;$d' > "$OUT"
[ -s "$OUT" ] || die "could not extract the AI report from $POD"
log "AI report saved: $OUT"
python3 - "$OUT" <<'PY'
import json, sys
r = json.load(open(sys.argv[1]))
m = r["metrics"]
print(f"\n  experiment={r['experiment']}  app={r['app_version']}")
print(f"  availability during fault : {m['availability_during_fault']*100:.1f}%   (SLO {r['slo']*100:.0f}%)")
print(f"  SLO breach                : {m['slo_breach_seconds']}s    MTTR: {m['mttr_seconds']}s    time-to-detect: {m['time_to_detect_seconds']}s")
print(f"  AI action                 : {r['action']}  ({r['action_reason']})")
for i in r["insights"]:
    print("   -", i)
PY
