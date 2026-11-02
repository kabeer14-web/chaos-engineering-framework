"""Synthetic user. Sends a constant request rate to the frontend and exports what a real user
would experience (success / error / latency) as Prometheus metrics. These metrics are the
steady-state signal for every chaos experiment."""
import os
import time
from concurrent.futures import ThreadPoolExecutor

import requests
from prometheus_client import Counter, Histogram, start_http_server

TARGET = os.getenv("TARGET_URL", "http://frontend.app:8080/")
RPS = float(os.getenv("RPS", "10"))
TIMEOUT = float(os.getenv("TIMEOUT", "3"))

REQS = Counter("loadgen_requests_total", "Requests sent by the load generator", ["result"])
LAT = Histogram(
    "loadgen_request_duration_seconds",
    "End-to-end latency seen by the synthetic user",
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 3.0),
)


def hit():
    t0 = time.perf_counter()
    try:
        ok = requests.get(TARGET, timeout=TIMEOUT).status_code == 200
    except requests.RequestException:
        ok = False
    LAT.observe(time.perf_counter() - t0)
    REQS.labels("ok" if ok else "error").inc()


def main():
    start_http_server(9100)
    pool = ThreadPoolExecutor(max_workers=64)
    interval = 1.0 / RPS
    nxt = time.perf_counter()
    while True:
        pool.submit(hit)
        nxt += interval
        time.sleep(max(0.0, nxt - time.perf_counter()))


if __name__ == "__main__":
    main()
