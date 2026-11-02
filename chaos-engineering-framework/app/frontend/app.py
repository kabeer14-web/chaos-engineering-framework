"""Frontend microservice: calls the backend. Resilience behaviour is controlled by env vars
so the same image is used for the weak (v1) and hardened (v2) deployments."""
import logging
import os

import requests
from flask import Flask, jsonify

import telemetry

app = Flask(__name__)
telemetry.init("frontend", app)
log = logging.getLogger("frontend")

BACKEND_URL = os.getenv("BACKEND_URL", "http://backend.app:8080")
TIMEOUT = float(os.getenv("BACKEND_TIMEOUT", "1.0"))
RETRIES = int(os.getenv("BACKEND_RETRIES", "0"))


@app.route("/")
def index():
    last_error = None
    for attempt in range(1, RETRIES + 2):
        try:
            # A fresh connection per attempt lets kube-proxy pick another backend replica.
            resp = requests.get(f"{BACKEND_URL}/api/data", timeout=TIMEOUT)
            resp.raise_for_status()
            return jsonify(ok=True, attempts=attempt, backend=resp.json())
        except requests.RequestException as exc:
            last_error = type(exc).__name__
            log.warning("backend call failed attempt=%d error=%s", attempt, last_error)
    log.error("backend unavailable after %d attempt(s)", RETRIES + 1)
    return jsonify(ok=False, error=last_error), 502
