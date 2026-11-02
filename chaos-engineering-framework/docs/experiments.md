# Experiment catalogue

Method for every experiment: **steady state -> hypothesis -> inject -> observe -> release -> AI analysis -> improve -> re-test**.
Steady-state signal: user success rate >= 99 % (SLO) and p95 latency, measured by the synthetic user (`loadgen`).
Blast radius: namespace `app` only; the infra node (monitoring, load generator, Argo) is never a target.
Abort condition: `kubectl delete -f k8s/chaos/<experiment>.yaml` (the workflow also removes it after the hold period).

| # | Failure type | Tool | Injection | Hypothesis (v1 weak) | Hypothesis (v2 hardened) |
|---|---|---|---|---|---|
| 1 | Service outage | Chaos Mesh PodChaos | kill one backend pod | single replica -> errors until pod is recreated | 3 replicas + probes + retries -> ~no user impact |
| 2 | Network latency | Chaos Mesh NetworkChaos | +1500 ms on traffic leaving a backend pod | 1 s client timeout -> errors | retries reach a healthy replica -> small impact |
| 3 | Resource exhaustion | Chaos Mesh StressChaos | 2 CPU workers at 100 % in backend pods | latency up, errors | HPA adds replicas, redundancy absorbs |
| 4 | Node failure | Ansible (`docker stop` kind node) | stop the node that runs a backend pod | pod unreachable until node returns (default 300 s eviction) | 20 s eviction, replicas on other node keep serving |

Run: `make experiment EXP=pod-kill|network-delay|cpu-stress`, `make node-failure`, or everything with `make suite`.

## Resilience measurement
- **Availability during fault** = mean user success rate between injection and release.
- **SLO breach seconds** = time success rate < 99 % after injection.
- **MTTR** = from first user-visible failure until success rate is back above the SLO.
- **Time-to-detect** = injection until the anomaly model first flags the system.
- **Blast radius / redundancy** = minimum available backend replicas during the fault.

## AIOps feedback loop
1. Prometheus holds metrics; Loki logs; Jaeger traces (all three correlated by `trace_id`).
2. `aiops/analyze.py` trains an Isolation Forest on the pre-injection baseline, adds a robust z-score guard, flags anomalies, computes the KPIs and writes insights.
3. It decides an action (`scale:backend:N` or `none`); the Argo workflow executes it (automated remediation).
4. The hardening changes (v2) are the permanent version of that insight; re-running the suite proves the improvement with numbers.
