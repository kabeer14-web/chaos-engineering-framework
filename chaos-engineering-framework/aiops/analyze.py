#!/usr/bin/env python3
"""AIOps analysis for one chaos experiment.

Pulls the experiment window from Prometheus, learns what "normal" looks like from the baseline period
(unsupervised Isolation Forest), flags abnormal behaviour during/after fault injection, computes
resilience KPIs (availability, MTTR, time-to-detect ...), writes human readable insights and decides on a
remediation action that the workflow then executes (the feedback loop).

Usage (inside the cluster the Argo workflow runs this; locally use a port-forward to Prometheus):
  python analyze.py --prom http://localhost:9090 --start T0 --inject T1 --release T2 \
                    --experiment pod-kill --label v1
"""
import argparse
import json
import sys
import time

import numpy as np
import requests
from sklearn.ensemble import IsolationForest

STEP = 5            # seconds between samples (Prometheus scrape interval of the app is 5s)
SLO = 0.99          # availability objective seen by the synthetic user
FEATURES = ["success_rate", "p95_latency", "error_rps", "backend_cpu", "backend_replicas"]
# Minimum "meaningful" spread per feature; stops tiny noise looking anomalous when the baseline is very flat.
MIN_STD = np.array([0.01, 0.02, 0.1, 0.02, 0.5])

QUERIES = {
    "success_rate": 'sum(rate(loadgen_requests_total{result="ok"}[15s])) / sum(rate(loadgen_requests_total[15s]))',
    "p95_latency": "histogram_quantile(0.95, sum(rate(loadgen_request_duration_seconds_bucket[15s])) by (le))",
    "error_rps": 'sum(rate(loadgen_requests_total{result="error"}[15s]))',
    "backend_cpu": 'sum(rate(container_cpu_usage_seconds_total{namespace="app",pod=~"backend-.*",container="backend"}[30s]))',
    "backend_replicas": 'kube_deployment_status_replicas_available{namespace="app",deployment="backend"}',
}


# --------------------------------------------------------------------------- data access
def prom_range(base, query, start, end, step=STEP):
    resp = requests.get(
        f"{base}/api/v1/query_range",
        params={"query": query, "start": start, "end": end, "step": step},
        timeout=30,
    )
    resp.raise_for_status()
    result = resp.json()["data"]["result"]
    if not result:
        return {}
    return {int(float(t)): float(v) for t, v in result[0]["values"]}


def fetch(base, start, end):
    return {name: prom_range(base, q, start, end) for name, q in QUERIES.items()}


# --------------------------------------------------------------------------- analysis (pure functions)
def build_frame(series, start, end):
    """Align all series on one time axis; forward-fill gaps."""
    ts = list(range(start, end + 1, STEP))
    cols = []
    for name in FEATURES:
        raw = series.get(name, {})
        col, last = [], None
        for t in ts:
            # accept samples within +-STEP/2 of the grid point
            v = next((raw[t + d] for d in (0, -1, 1, -2, 2) if (t + d) in raw), None)
            if v is None or (isinstance(v, float) and np.isnan(v)):
                v = last
            col.append(np.nan if v is None else v)
            last = col[-1] if not np.isnan(col[-1]) else last
        cols.append(col)
    X = np.array(cols, dtype=float).T
    # leading NaNs (no data yet): assume the healthy defaults
    defaults = np.array([1.0, 0.0, 0.0, 0.0, np.nan])
    for j in range(X.shape[1]):
        mask = np.isnan(X[:, j])
        if mask.any():
            fill = defaults[j] if not np.isnan(defaults[j]) else np.nanmedian(X[:, j]) if (~mask).any() else 1.0
            X[mask, j] = fill
    return np.array(ts), X


Z_CONFIRM = 3.0     # an Isolation Forest flag only counts if some metric is also >3 baseline-sigmas away
Z_EXTREME = 6.0     # a metric >6 baseline-sigmas away is anomalous on its own (see detect_anomalies)


def detect_anomalies(ts, X, inject_ts):
    """Ensemble detector trained on the pre-injection baseline only.

    1. Isolation Forest (multivariate, unsupervised) scores how unusual each sample is overall.
    2. A robust z-score guard measures how many baseline-sigmas the worst metric is away from normal.

    Why both: tree models cannot extrapolate beyond the range they were trained on, so a 100% outage
    can score no higher than the most extreme baseline sample (the unit tests caught exactly this), while
    jitter in a flat baseline can make healthy samples look unusual. The ensemble flags a sample when
    the z-score is extreme, or when Isolation Forest flags it AND the z-score confirms it.

    Returns (flags, scores, zmax): boolean flags, Isolation Forest score (higher = more abnormal),
    and the per-sample worst z-score.
    """
    base_mask = ts < inject_ts
    if base_mask.sum() < 6:        # not enough baseline: learn from the whole window
        base_mask = np.ones_like(base_mask, dtype=bool)
    base = X[base_mask]
    mean = base.mean(axis=0)
    std = np.maximum(base.std(axis=0), MIN_STD)
    scale = lambda A: (A - mean) / std
    rng = np.random.RandomState(42)
    train = scale(base) + rng.normal(0, 0.05, size=base.shape)   # jitter so flat baselines still give splittable data
    model = IsolationForest(n_estimators=200, contamination=0.01, random_state=42).fit(train)
    forest_flag = model.predict(scale(X)) == -1
    scores = -model.score_samples(scale(X))                      # higher = more abnormal
    zmax = np.abs(scale(X)).max(axis=1)
    flags = (zmax >= Z_EXTREME) | (forest_flag & (zmax >= Z_CONFIRM))
    return flags, scores, zmax


def outage_and_mttr(ts, success, inject_ts):
    """Return (impact_start_ts, recovery_ts, mttr_seconds, recovered).

    Impact starts at the first sample after injection below SLO. Recovery = first moment after that
    where 3 consecutive samples are back at/above SLO. If the SLO is never violated there is no impact.
    """
    idx = np.where(ts >= inject_ts)[0]
    if len(idx) == 0:
        return None, None, 0, True
    breach = [i for i in idx if success[i] < SLO]
    if not breach:
        return None, None, 0, True
    i0 = breach[0]
    for j in range(i0 + 1, len(ts) - 2):
        if all(success[j + k] >= SLO for k in range(3)):
            return int(ts[i0]), int(ts[j]), int(ts[j] - ts[i0]), True
    return int(ts[i0]), None, int(ts[-1] - ts[i0]), False


def analyze(series, start, end, inject, release, experiment, label):
    ts, X = build_frame(series, start, end)
    col = {n: X[:, i] for i, n in enumerate(FEATURES)}
    flags, scores, zmax = detect_anomalies(ts, X, inject)
    fault = (ts >= inject) & (ts <= release)
    after_inject = ts >= inject

    impact_ts, recovery_ts, mttr, recovered = outage_and_mttr(ts, col["success_rate"], inject)
    anomalous_after = ts[flags & after_inject]
    time_to_detect = int(anomalous_after[0] - inject) if len(anomalous_after) else None

    fault_sr = col["success_rate"][fault]
    availability = float(np.mean(fault_sr)) if len(fault_sr) else 1.0
    min_success = float(np.min(fault_sr)) if len(fault_sr) else 1.0
    slo_breach_seconds = int(np.sum(col["success_rate"][after_inject] < SLO) * STEP)
    min_replicas = float(np.min(col["backend_replicas"][after_inject])) if after_inject.any() else 0.0
    baseline_sr = float(np.mean(col["success_rate"][ts < inject])) if (ts < inject).any() else 1.0

    metrics = {
        "baseline_success_rate": round(baseline_sr, 4),
        "availability_during_fault": round(availability, 4),
        "min_success_rate": round(min_success, 4),
        "slo_breach_seconds": slo_breach_seconds,
        "mttr_seconds": mttr,
        "recovered": recovered,
        "time_to_impact_seconds": None if impact_ts is None else int(impact_ts - inject),
        "time_to_detect_seconds": time_to_detect,
        "max_p95_latency_seconds": round(float(np.max(col["p95_latency"][after_inject])), 3) if after_inject.any() else 0,
        "max_backend_cpu_cores": round(float(np.max(col["backend_cpu"][after_inject])), 3) if after_inject.any() else 0,
        "min_backend_replicas_available": min_replicas,
        "anomalous_samples": int(flags[after_inject].sum()),
        "total_samples_after_injection": int(after_inject.sum()),
        "max_anomaly_score": round(float(scores.max()), 3),
        "max_z_score": round(float(zmax[after_inject].max()), 1) if after_inject.any() else 0,
    }
    insights = build_insights(metrics, experiment)
    action, reason = decide_action(metrics, experiment)
    return {
        "experiment": experiment,
        "app_version": label,
        "window": {"start": start, "inject": inject, "release": release, "end": end},
        "slo": SLO,
        "model": "IsolationForest(n_estimators=200) + robust z-score guard, trained on pre-injection baseline",
        "metrics": metrics,
        "insights": insights,
        "action": action,
        "action_reason": reason,
    }


def build_insights(m, experiment):
    out = []
    if m["slo_breach_seconds"] == 0:
        out.append(f"No user-visible impact: availability stayed at or above the {int(SLO*100)}% SLO during '{experiment}'. "
                   "The system absorbed the failure.")
    else:
        out.append(f"User impact detected: SLO was breached for {m['slo_breach_seconds']}s; availability during the fault was "
                   f"{m['availability_during_fault']*100:.1f}% (lowest {m['min_success_rate']*100:.1f}%).")
        if m["recovered"]:
            out.append(f"The system recovered on its own; outage lasted about {m['mttr_seconds']}s (MTTR, +/-15s metric smoothing).")
        else:
            out.append("The system had NOT recovered when the observation window ended.")
    if m["min_backend_replicas_available"] <= 1 and m["slo_breach_seconds"] > 0:
        out.append("Single point of failure: at most one backend replica was available while users were impacted. "
                   "Recommendation: run >=3 replicas spread over nodes, add readiness probes and a PodDisruptionBudget.")
    if m["max_p95_latency_seconds"] >= 1.0:
        out.append(f"Latency degradation: p95 reached {m['max_p95_latency_seconds']}s. Recommendation: client timeouts + retries "
                   "to healthy replicas, and horizontal autoscaling.")
    if m["time_to_detect_seconds"] is not None:
        out.append(f"The anomaly model flagged abnormal behaviour {m['time_to_detect_seconds']}s after injection "
                   f"({m['anomalous_samples']} of {m['total_samples_after_injection']} samples).")
    elif m["slo_breach_seconds"] > 0:
        out.append("The anomaly model did not flag the incident although the SLO was breached - baseline may be too noisy; review thresholds.")
    return out


def decide_action(m, experiment):
    """Feedback loop: translate the analysis into an automated remediation (executed by the workflow)."""
    if m["slo_breach_seconds"] > 0 and m["min_backend_replicas_available"] <= 1:
        return "scale:backend:3", "SLO breached with <=1 backend replica available: restore redundancy (scale backend to 3)."
    if m["slo_breach_seconds"] > 0 and m["max_backend_cpu_cores"] > 0.4:
        return "scale:backend:4", "SLO breached while backend CPU was saturated: add capacity (scale backend to 4)."
    return "none", "System met the SLO or already had enough redundancy; no remediation required."


# --------------------------------------------------------------------------- CLI
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--prom", default="http://localhost:9090")
    ap.add_argument("--start", type=int, required=True)
    ap.add_argument("--inject", type=int, required=True)
    ap.add_argument("--release", type=int, required=True)
    ap.add_argument("--end", type=int, default=None)
    ap.add_argument("--experiment", required=True)
    ap.add_argument("--label", default="unknown")
    ap.add_argument("--action-file", default=None)
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    end = a.end or int(time.time())

    series = fetch(a.prom, a.start, end)
    if not series["success_rate"]:
        print("ERROR: no loadgen metrics returned by Prometheus for the window", file=sys.stderr)
        if a.action_file:
            open(a.action_file, "w").write("none")
        sys.exit(2)

    report = analyze(series, a.start, end, a.inject, a.release, a.experiment, a.label)
    text = json.dumps(report, indent=2)
    print("===REPORT-BEGIN===")
    print(text)
    print("===REPORT-END===")
    if a.out:
        open(a.out, "w").write(text)
    if a.action_file:
        open(a.action_file, "w").write(report["action"])


if __name__ == "__main__":
    main()
