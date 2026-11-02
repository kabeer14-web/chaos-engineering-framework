#!/usr/bin/env python3
"""Before/after comparison of all experiment reports in results/ (v1 weak vs v2 hardened).

Writes results/summary.md (table for README / slides) and results/summary.png (chart) when matplotlib exists.
Only real measured numbers are used - the script never invents values.
Usage: python aiops/compare.py [results_dir]
"""
import glob
import json
import os
import sys

EXPERIMENTS = ["pod-kill", "network-delay", "cpu-stress", "node-failure"]
VERSIONS = ["v1", "v2"]


def load(results_dir):
    latest = {}
    for path in sorted(glob.glob(os.path.join(results_dir, "*.json"))):   # file names start with a timestamp
        try:
            r = json.load(open(path))
            latest[(r["app_version"], r["experiment"])] = r      # later file wins
        except (ValueError, KeyError):
            continue
    return latest


def fmt(v, suffix=""):
    return "-" if v is None else f"{v}{suffix}"


def table(latest):
    rows = ["| Experiment | App | Availability during fault | SLO breach | MTTR | Detected after | Max p95 | AI action |",
            "|---|---|---|---|---|---|---|---|"]
    for exp in EXPERIMENTS:
        for ver in VERSIONS:
            r = latest.get((ver, exp))
            if not r:
                continue
            m = r["metrics"]
            rows.append(
                f"| {exp} | {ver} | {m['availability_during_fault']*100:.1f}% | {m['slo_breach_seconds']}s | "
                f"{fmt(m['mttr_seconds'], 's')} | {fmt(m['time_to_detect_seconds'], 's')} | "
                f"{m['max_p95_latency_seconds']}s | {r['action']} |")
    return "\n".join(rows)


def chart(latest, out):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("matplotlib not installed - skipping chart (pip install matplotlib)")
        return
    fig, axes = plt.subplots(1, 2, figsize=(11, 4))
    width = 0.38
    for ax, key, title, scale in ((axes[0], "availability_during_fault", "Availability during fault (%)", 100),
                                  (axes[1], "slo_breach_seconds", "SLO breach (seconds)", 1)):
        for i, ver in enumerate(VERSIONS):
            vals = [(latest[(ver, e)]["metrics"][key] * scale) if (ver, e) in latest else 0 for e in EXPERIMENTS]
            ax.bar([x + i * width for x in range(len(EXPERIMENTS))], vals, width, label=ver,
                   color=["#c0392b", "#27ae60"][i])
        ax.set_xticks([x + width / 2 for x in range(len(EXPERIMENTS))])
        ax.set_xticklabels(EXPERIMENTS, rotation=15)
        ax.set_title(title)
        ax.legend()
    fig.suptitle("Resilience before (v1) vs after (v2) - measured")
    fig.tight_layout()
    fig.savefig(out, dpi=130)
    print("chart:", out)


def main():
    d = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(__file__), "..", "results")
    latest = load(d)
    if not latest:
        sys.exit(f"no reports found in {d}")
    md = table(latest)
    print(md)
    open(os.path.join(d, "summary.md"), "w").write(md + "\n")
    chart(latest, os.path.join(d, "summary.png"))


if __name__ == "__main__":
    main()
