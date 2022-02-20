#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright (C) 2022 Sean Anderson <seanga2@gmail.com>
# Copyright (c) 2017 Viktor Adam
# Portions of this file are adapted from prometheus_flask_exporter

import time
import random

from flask import Flask
from mpmetrics.flask import PrometheusMetrics

app = Flask(__name__)
PrometheusMetrics(app)

@app.route("/one")
def first_route():
    time.sleep(random.random() * 0.2)
    return "ok"

@app.route("/two")
def the_second():
    time.sleep(random.random() * 0.4)
    return "ok"

@app.route("/three")
def test_3rd():
    time.sleep(random.random() * 0.6)
    return "ok"

@app.route("/four")
def fourth_one():
    time.sleep(random.random() * 0.8)
    return "ok"

@app.route("/error")
def oops():
    return ":(", 500

if __name__ == "__main__":
    app.run("0.0.0.0", 8000, threaded=True)
