#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright (C) 2022 Sean Anderson <seanga2@gmail.com>
# Copyright (c) 2017 Viktor Adam
# Portions of this file are adapted from prometheus_flask_exporter

import time
import random
import multiprocessing
import requests

endpoints = ("one", "two", "three", "four", "error")
HOST = "http://localhost:8000/"

def run():
    while True:
        try:
            target = random.choice(endpoints)
            requests.get(HOST + target, timeout=1)
        except requests.RequestException:
            print("cannot connect", HOST)
            time.sleep(1)

if __name__ == "__main__":
    for _ in range(4):
        thread = multiprocessing.Process(target=run)
        thread.start()
    run()
