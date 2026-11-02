"""Backend microservice: returns a small payload after doing a fixed amount of CPU work."""
import logging
import os
import random
import socket

from flask import Flask, jsonify

import telemetry

app = Flask(__name__)
telemetry.init("backend", app)
log = logging.getLogger("backend")

# Fixed amount of CPU work per request (so CPU contention shows up as latency).
WORK_ITERS = int(os.getenv("WORK_ITERS", "60000"))
FAIL_RATE = float(os.getenv("FAIL_RATE", "0"))


def burn(iterations):
    total = 0
    for i in range(iterations):
        total += i * i
    return total


@app.route("/api/data")
def data():
    burn(WORK_ITERS)
    if random.random() < FAIL_RATE:
        log.error("injected application error")
        return jsonify(error="injected failure"), 500
    log.info("served /api/data")
    return jsonify(value=random.randint(1, 1000), pod=socket.gethostname())
