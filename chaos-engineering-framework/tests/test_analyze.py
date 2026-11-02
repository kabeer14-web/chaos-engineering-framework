"""Unit tests for the AIOps analysis using synthetic Prometheus series (no cluster needed)."""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "aiops"))
import analyze  # noqa: E402

START, INJECT, RELEASE, END = 1000, 1060, 1120, 1250


def make_series(fault_fn, replicas_fn, seed=1):
    rng = np.random.RandomState(seed)
    s = {k: {} for k in analyze.FEATURES}
    for t in range(START, END + 1, analyze.STEP):
        sr, lat, err, cpu = fault_fn(t)
        s["success_rate"][t] = sr + rng.normal(0, 0.001)
        s["p95_latency"][t] = lat + abs(rng.normal(0, 0.002))
        s["error_rps"][t] = err
        s["backend_cpu"][t] = cpu + abs(rng.normal(0, 0.005))
        s["backend_replicas"][t] = replicas_fn(t)
    return s


def test_weak_system_outage_is_detected_and_remediated():
    # v1: total outage from INJECT for 25s, single replica
    def fault(t):
        if INJECT <= t < INJECT + 25:
            return 0.0, 2.9, 10.0, 0.01
        return 1.0, 0.02, 0.0, 0.05

    rep = analyze.analyze(make_series(fault, lambda t: 1.0), START, END, INJECT, RELEASE, "pod-kill", "v1")
    m = rep["metrics"]
    assert m["slo_breach_seconds"] > 0
    assert m["recovered"] is True
    assert 20 <= m["mttr_seconds"] <= 35
    assert m["time_to_detect_seconds"] is not None and m["time_to_detect_seconds"] <= 10
    assert rep["action"] == "scale:backend:3"
    assert any("Single point of failure" in i for i in rep["insights"])


def test_hardened_system_shows_no_impact_and_no_action():
    def fault(t):
        return 1.0, 0.03, 0.0, 0.06

    def replicas(t):
        return 3.0

    rep = analyze.analyze(make_series(fault, replicas), START, END, INJECT, RELEASE, "pod-kill", "v2")
    m = rep["metrics"]
    assert m["slo_breach_seconds"] == 0
    assert m["mttr_seconds"] == 0
    assert rep["action"] == "none"
    assert any("No user-visible impact" in i for i in rep["insights"])


def test_not_recovered_is_reported():
    def fault(t):
        return (0.0, 3.0, 10.0, 0.01) if t >= INJECT else (1.0, 0.02, 0.0, 0.05)

    rep = analyze.analyze(make_series(fault, lambda t: 1.0), START, END, INJECT, RELEASE, "node-failure", "v1")
    assert rep["metrics"]["recovered"] is False


def test_cpu_saturation_leads_to_capacity_action():
    def fault(t):
        if INJECT <= t < RELEASE:
            return 0.8, 1.5, 2.0, 0.5
        return 1.0, 0.02, 0.0, 0.05

    rep = analyze.analyze(make_series(fault, lambda t: 2.0), START, END, INJECT, RELEASE, "cpu-stress", "v1")
    assert rep["action"] == "scale:backend:4"


def test_detector_flags_outage_immediately_and_not_healthy_samples():
    """Regression: Isolation Forest alone missed a 100% outage and flagged a healthy sample."""
    def fault(t):
        if INJECT <= t < INJECT + 25:
            return 0.0, 2.9, 10.0, 0.01
        return 1.0, 0.02, 0.0, 0.05

    ts, X = analyze.build_frame(make_series(fault, lambda t: 1.0), START, END)
    flags, _, zmax = analyze.detect_anomalies(ts, X, INJECT)
    outage = (ts >= INJECT) & (ts < INJECT + 25)
    assert flags[outage].all(), "every outage sample must be flagged"
    assert not flags[~outage].any(), "no healthy sample (before or after) may be flagged"
    assert zmax[outage].min() >= analyze.Z_EXTREME


def test_mild_latency_degradation_is_flagged_but_not_an_outage():
    def fault(t):
        if INJECT <= t < RELEASE:
            return 1.0, 0.5, 0.0, 0.09   # slower, but every request still succeeds
        return 1.0, 0.02, 0.0, 0.05

    rep = analyze.analyze(make_series(fault, lambda t: 3.0), START, END, INJECT, RELEASE, "network-delay", "v2")
    assert rep["metrics"]["slo_breach_seconds"] == 0
    assert rep["metrics"]["time_to_detect_seconds"] is not None
    assert rep["action"] == "none"
