# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2022 Sean Anderson <seanga2@gmail.com>

from contextlib import contextmanager
import datetime
import time

from freezegun import freeze_time
from freezegun.api import fake_monotonic
time.perf_counter = fake_monotonic

import pytest
from prometheus_client.parser import text_string_to_metric_families

import examples.flask_server
from examples.flask_server import app
app.config['TESTING'] = True

@contextmanager
def sleeping_freeze_time(*args, **kwargs):
    with freeze_time(*args, **kwargs) as frozen:
        real_sleep = time.sleep
        time.sleep = frozen.tick
        yield frozen
        time.sleep = real_sleep

def test_flask_server():
    client = app.test_client()
    with sleeping_freeze_time():
        assert client.get('/one').status_code == 200
        assert client.get('/two').status_code == 200
        assert client.get('/three').status_code == 200
        assert client.get('/four').status_code == 200
        assert client.get('/error').status_code == 500

    resp = client.get('/metrics')
    assert resp.status_code == 200

    name = 'flask_http_request_duration_seconds'
    for metric in text_string_to_metric_families(resp.data.decode('utf-8')):
        if metric.name == name:
            break

    def get_sample(name, endpoint, le, method, status):
        for sample in metric.samples:
            if sample.name == name \
               and sample.labels['endpoint'] == endpoint \
               and sample.labels['le'] == le \
               and sample.labels['method'] == method \
               and sample.labels['status'] == status:
                return sample
        raise KeyError

    assert get_sample(name + '_bucket', 'first_route', '0.25', 'GET', '200').value == 1.0
    assert get_sample(name + '_bucket', 'the_second', '0.5', 'GET', '200').value == 1.0
    assert get_sample(name + '_bucket', 'test_3rd', '0.75', 'GET', '200').value == 1.0
    assert get_sample(name + '_bucket', 'fourth_one', '1.0', 'GET', '200').value == 1.0
    assert get_sample(name + '_bucket', 'oops', '0.005', 'GET', '500').value == 1.0
