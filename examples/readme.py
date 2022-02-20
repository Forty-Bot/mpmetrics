#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright (C) 2022 Sean Anderson <seanga2@gmail.com>
# Copyright 2015 The Prometheus Authors
# Portions of this file are adapted from prometheus_client

from mpmetrics import Summary
from prometheus_client import start_http_server
import multiprocessing
import random
import time

# Create a metric to track time spent and requests made.
REQUEST_TIME = Summary('request_processing_seconds', 'Time spent processing request')

# Decorate function with metric.
@REQUEST_TIME.time()
def process_request(t):
    """A dummy function that takes some time."""
    time.sleep(t)

# Function to generate requests
def generate_requests():
    while True:
        process_request(random.random())

if __name__ == '__main__':
    # Start up the server to expose the metrics.
    start_http_server(8000)
    # Generate some requests from two processes
    multiprocessing.Process(target=generate_requests).start()
    generate_requests()
