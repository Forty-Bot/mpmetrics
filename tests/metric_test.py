# SPDX-License-Identifier: GPL-3.0-only AND Apache-2.0
# Copyright (C) 2022 Sean Anderson <seanga2@gmail.com>
# Copyright 2015 The Prometheus Authors
# Portions of this file are adapted from prometheus_client

from contextlib import nullcontext
import pickle
import random
import time

from hypothesis import given, strategies as st
from prometheus_client.registry import CollectorRegistry
import pytest

from mpmetrics.metrics import Counter, Gauge, Summary, Histogram
from mpmetrics.atomic import AtomicUInt64

from .common import heap, parallel, parallels, ParallelLoop

@pytest.fixture(scope='session')
def registry(heap):
    class FakeRegistry:
        def register(self, collector):
            pass

    return FakeRegistry()

def get_sample_value(collector, name, labels={}):
    for metric in collector.collect():
        for s in metric.samples:
            if s.name == name and s.labels == labels:
                return s.value
    return None

class TestCounter:
    @pytest.fixture
    def counter(self, registry):
        return Counter('c_total', "help", registry=registry)

    def test_increment(self, counter):
        assert get_sample_value(counter, 'c_created')
        assert get_sample_value(counter, 'c_total') == 0
        counter.inc()
        assert get_sample_value(counter, 'c_total') == 1
        counter.inc(7)
        assert get_sample_value(counter, 'c_total') == 8
        with pytest.raises(OverflowError):
            counter.inc(AtomicUInt64.max)

    @given(st.integers(max_value=-1))
    def test_negative_increment_raises(self, registry, amount):
        counter = Counter('c_total', "help", registry=registry)
        with pytest.raises(ValueError):
            counter.inc(amount)

    def test_exceptions(self, counter):
        for exception in (ValueError, TypeError):
            try:
                with counter.count_exceptions(ValueError):
                    raise exception
            except:
                pass

        assert get_sample_value(counter, 'c_total') == 1

        for x in range(2):
            try:
                counter.count_exceptions(ZeroDivisionError)(lambda: 1/x)()
            except:
                pass

        assert get_sample_value(counter, 'c_total') == 2

    def test_concurrent(self, counter, parallel):
        class Test(ParallelLoop):
            def __init__(self):
                super().__init__(parallel)
                self.counter = counter

            def loop(self, n):
                self.counter.inc()

            def final(self):
                assert get_sample_value(self.counter, 'c_total') == self.total 

        Test().run()

class TestGauge:
    @pytest.fixture
    def gauge(self, registry):
        return Gauge('g', 'help', registry=registry)

    def test_gauge(self, gauge):
        assert get_sample_value(gauge, 'g') == 0
        gauge.inc()
        assert get_sample_value(gauge, 'g') == 1
        gauge.dec(3)
        assert get_sample_value(gauge, 'g') == -2
        gauge.set(9)
        assert get_sample_value(gauge, 'g') == 9

    def test_inprogress(self, gauge):
        @gauge.track_inprogress()
        def test():
            assert get_sample_value(gauge, 'g') == 1
            with gauge.track_inprogress():
                assert get_sample_value(gauge, 'g') == 2
                raise Exception
            assert get_sample_value(gauge, 'g') == 1

        try:
            test()
        except:
            pass
        assert get_sample_value(gauge, 'g') == 0

    def test_concurrent(self, gauge, parallel):
        class Test(ParallelLoop):
            def __init__(self):
                super().__init__(parallel)
                self.gauge = gauge

            def loop(self, n):
                self.gauge.inc(1)

            def final(self):
                assert get_sample_value(self.gauge, 'g') == self.total
            
        Test().run()

class TestSummary:
    @pytest.fixture
    def summary(self, registry):
        return Summary('s', 'help', registry=registry)

    def test_summary(self, summary):
        assert get_sample_value(summary, 's_created')
        assert get_sample_value(summary, 's_count') == 0
        assert get_sample_value(summary, 's_sum') == 0
        summary.observe(10)
        assert get_sample_value(summary, 's_count') == 1
        assert get_sample_value(summary, 's_sum') == 10

    def test_concurrent(self, summary, parallel):
        class Test(ParallelLoop):
            def __init__(self):
                super().__init__(parallel)
                self.summary = summary

            def get_samples(self):
                metric = next(self.summary.collect())
                for s in metric.samples:
                    if s.name.endswith('s_count'):
                        count = s.value
                    elif s.name.endswith('s_sum'):
                        sum = s.value
                return count, sum

            def loop(self, n):
                self.summary.observe(1)

            def check(self):
                count, sum = self.get_samples()
                assert count == sum

            def final(self):
                count, sum = self.get_samples()
                assert count == self.total
                assert sum == self.total
            
        Test().run()

class TestHistogram:
    @pytest.fixture
    def histogram(self, registry):
        return Histogram('h', 'help', registry=registry)

    @pytest.fixture
    def labels(self, registry):
        return Histogram('h', 'help', ['l'], registry=registry)

    def test_histogram(self, histogram):
        assert get_sample_value(histogram, 'h_created')
        assert get_sample_value(histogram, 'h_bucket', {'le': '1.0'}) == 0
        assert get_sample_value(histogram, 'h_bucket', {'le': '2.5'}) == 0
        assert get_sample_value(histogram, 'h_bucket', {'le': '5.0'}) == 0
        assert get_sample_value(histogram, 'h_bucket', {'le': 'inf'}) == 0
        assert get_sample_value(histogram, 'h_count') == 0
        assert get_sample_value(histogram, 'h_sum') == 0

        histogram.observe(2)
        assert get_sample_value(histogram, 'h_bucket', {'le': '1.0'}) == 0
        assert get_sample_value(histogram, 'h_bucket', {'le': '2.5'}) == 1
        assert get_sample_value(histogram, 'h_bucket', {'le': '5.0'}) == 1
        assert get_sample_value(histogram, 'h_bucket', {'le': 'inf'}) == 1
        assert get_sample_value(histogram, 'h_count') == 1
        assert get_sample_value(histogram, 'h_sum') == 2

        histogram.observe(2.5)
        assert get_sample_value(histogram, 'h_bucket', {'le': '1.0'}) == 0
        assert get_sample_value(histogram, 'h_bucket', {'le': '2.5'}) == 2
        assert get_sample_value(histogram, 'h_bucket', {'le': '5.0'}) == 2
        assert get_sample_value(histogram, 'h_bucket', {'le': 'inf'}) == 2
        assert get_sample_value(histogram, 'h_count') == 2
        assert get_sample_value(histogram, 'h_sum') == 4.5

        histogram.observe(float("inf"))
        assert get_sample_value(histogram, 'h_bucket', {'le': '1.0'}) == 0
        assert get_sample_value(histogram, 'h_bucket', {'le': '2.5'}) == 2
        assert get_sample_value(histogram, 'h_bucket', {'le': '5.0'}) == 2
        assert get_sample_value(histogram, 'h_bucket', {'le': 'inf'}) == 3
        assert get_sample_value(histogram, 'h_count') == 3
        assert get_sample_value(histogram, 'h_sum') == float("inf")

    def test_setting_buckets(self, registry):
        def get_buckets(h):
            buckets = []
            for sample in next(h.collect()).samples:
                if sample.name != 'h_bucket':
                    continue
                buckets.append(float(sample.labels['le']))
            return buckets

        h = Histogram('h', 'help', registry=registry, buckets=[0, 1, 2])
        assert get_buckets(h) == [0.0, 1.0, 2.0, float("inf")]

        h = Histogram('h', 'help', registry=registry, buckets=[0, 1, 2, float("inf")])
        assert get_buckets(h) == [0.0, 1.0, 2.0, float("inf")]

        with pytest.raises(ValueError):
            Histogram('h', 'help', registry=registry, buckets=[])

        with pytest.raises(ValueError):
            Histogram('h', 'help', registry=registry, buckets=[float('inf')])

        with pytest.raises(ValueError):
            Histogram('h', 'help', registry=registry, buckets=[3, 1])

    def test_invalid_labels(self, registry):
        with pytest.raises(ValueError):
            Histogram('h', 'help', registry=registry, labelnames=['le'])

    def test_labels(self, labels):
        labels.labels('a').observe(2)
        assert get_sample_value(labels, 'h_bucket', {'le': '1.0', 'l': 'a'}) == 0
        assert get_sample_value(labels, 'h_bucket', {'le': '2.5', 'l': 'a'}) == 1
        assert get_sample_value(labels, 'h_bucket', {'le': '5.0', 'l': 'a'}) == 1
        assert get_sample_value(labels, 'h_bucket', {'le': 'inf', 'l': 'a'}) == 1
        assert get_sample_value(labels, 'h_count', {'l': 'a'}) == 1
        assert get_sample_value(labels, 'h_sum', {'l': 'a'}) in (2, None)

    def test_concurrent(self, histogram, parallel):
        class Test(ParallelLoop):
            def __init__(self, parallel):
                super().__init__(parallel)
                self.histogram = histogram

            def get_sample(self):
                metric = next(self.histogram.collect())
                buckets = []
                for s in metric.samples:
                    if s.name.endswith('h_bucket'):
                        buckets.append(s.value)
                    elif s.name.endswith('h_sum'):
                        sum = s.value
                    elif s.name.endswith('h_count'):
                        count = s.value
                return buckets, sum, count

            def loop(self, n):
                self.histogram.observe(random.sample(self.histogram.thresholds, 1))

            def check(self):
                buckets, sum, count = self.get_sample()
                prev = 0
                for bucket, threshold in zip(buckets, self.histogram.thresholds):
                    bucket_sum += (bucket - prev) * threshold
                    prev = bucket
                assert sum == bucket_sum
                assert buckets[-1] == count

            def final(self):
                buckets, sum, count = self.get_sample()
                assert buckets[-1] == count == self.total

@pytest.mark.parametrize(('cls', 'name'), (
    (Gauge, 'm'),
    (Summary, 'm_sum'),
    (Histogram, 'm_sum'))
)
def test_time(registry, cls, name):
    metric = cls('m', 'help', registry=registry)
    with metric.time():
        time.sleep(0.001)
    assert get_sample_value(metric, name) >= 0.001

    metric = cls('m', 'help', registry=registry)
    metric.time()(time.sleep)(0.001)
    assert get_sample_value(metric, name) >= 0.001

@pytest.mark.parametrize('cls', (Counter, Gauge, Summary, Histogram))
def test_pickle(registry, cls):
    metric = cls('name', 'help', labelnames=('l'), registry=registry)
    pickle.loads(pickle.dumps(metric.labels('x')))

class TestEnum:
    @pytest.fixture
    def enum(self, registry):
        return Enum('e', 'help', states=['a', 'b', 'c'], registry=registry)

    @pytest.fixture
    def labels(self, registry):
        return Enum('el', 'help', ['l'], states=['a', 'b', 'c'], registry=registry)

    @pytest.mark.skip()
    def test_enum(self, enum, registry):
        assert get_sample_value(enum, 'e', {'e': 'a'}) == 1
        assert get_sample_value(enum, 'e', {'e': 'b'}) == 0
        assert get_sample_value(enum, 'e', {'e': 'c'}) == 0

        enum.state('b')
        assert get_sample_value(enum, 'e', {'e': 'a'}) == 0
        assert get_sample_value(enum, 'e', {'e': 'b'}) == 1
        assert get_sample_value(enum, 'e', {'e': 'c'}) == 0

        with pytest.raises(ValueError):
            enum.state('d')

        with pytest.raises(ValueError):
            Enum('e', 'help', registry=registry)

    @pytest.mark.skip()
    def test_labels(self, labels):
        labels.labels('a').state('c')
        assert get_sample_value(labels, 'el', {'l': 'a', 'el': 'a'}) == 0
        assert get_sample_value(labels, 'el', {'l': 'a', 'el': 'b'}) == 0
        assert get_sample_value(labels, 'el', {'l': 'a', 'el': 'c'}) == 1

    @pytest.mark.skip()
    def test_overlapping_labels(self, registry):
        with pytest.raises(ValueError):
            Enum('e', 'help', registry=registry, labelnames=['e'])

class TestLabelCollector:
    @pytest.fixture
    def counter(self, registry):
        return Counter('c_total', "help", labelnames=['l'], registry=registry)

    @pytest.fixture
    def two_labels(self, registry):
        return Counter('two', "help", labelnames=['a', 'b'], registry=registry)

    def test_child(self, counter, two_labels):
        counter.labels('x').inc()
        assert get_sample_value(counter, 'c_total', {'l': 'x'}) == 1
        two_labels.labels('x', 'y').inc(2)
        assert get_sample_value(two_labels, 'two_total', {'a': 'x', 'b': 'y'}) == 2

    def test_incorrect_label_count_raises(self, counter):
        with pytest.raises(ValueError):
            counter.labels()

        with pytest.raises(ValueError):
            counter.labels('a', 'b')

    def test_labels_on_labels(self, counter):
        with pytest.raises(AttributeError):
            counter.labels('a').labels('b')

    def test_labels_coerced_to_string(self, counter):
        counter.labels(None).inc()
        counter.labels(l=None).inc()
        assert get_sample_value(counter, 'c_total', {'l': 'None'}) == 2

    def test_non_string_labels_raises(self, counter):
        class Test:
            __str__ = None

        with pytest.raises(TypeError):
            counter.labels(Test())

        with pytest.raises(TypeError):
            counter.labels(l=Test())

    def test_namespace_subsystem_concatenated(self, registry):
        c = Counter('c_total', 'help', namespace='a', subsystem='b', registry=registry)
        assert c._name == 'a_b_c'

    def test_labels_by_kwarg(self, counter, two_labels):
        counter.labels(l='x').inc()
        assert get_sample_value(counter, 'c_total', {'l': 'x'}) == 1
        for kwargs in ({'l': 'x', 'm': 'y'}, {'m': 'y'}, {}):
            with pytest.raises(ValueError):
                counter.labels(**kwargs)

        two_labels.labels(a='x', b='y').inc()
        assert get_sample_value(two_labels, 'two_total', {'a': 'x', 'b': 'y'}) == 1
        for kwargs in (
            { 'a': 'x', 'b': 'y', 'c': 'z' },
            { 'a': 'x', 'c': 'z' },
            { 'b': 'y', 'c': 'z' },
            { 'c': 'z' }):
            with pytest.raises(ValueError):
                counter.labels(**kwargs)

        with pytest.raises(ValueError):
            two_labels.labels({'a': 'x'}, b='y')

    def test_invalid_names_raise(self, registry):
        for kwargs in (
            { 'name': '' },
            { 'name': '^' },
            { 'name': '', 'namespace': '&' },
            { 'name': '', 'subsystem': '(' },
            { 'name': 'c_total', 'labelnames': ['^'] },
            { 'name': 'c_total', 'labelnames': ['a:b'] },
            { 'name': 'c_total', 'labelnames': ['__reserved'] }):
            with pytest.raises(ValueError):
                Counter(**kwargs, documentation='', registry=registry)

        with pytest.raises(ValueError):
            Summary('c_total', '', labelnames=['quantile'], registry=registry)

    def test_empty_labels_list(self, registry):
        h = Histogram('h', 'help', [], registry=registry)
        assert get_sample_value(h, 'h_count') == 0

    def test_unit_appended(self, registry):
        h = Histogram('h', 'help', [], registry=registry, unit="seconds")
        assert h._name == 'h_seconds'

    def test_unit_notappended(self, registry):
        h = Histogram('h_seconds', 'help', [], registry=registry, unit="seconds")
        assert h._name == 'h_seconds'

    @pytest.mark.skip()
    def test_no_units_for_info_enum(self, registry):
        with pytest.raises(ValueError):
            Info('foo', 'help', unit="x")

        with pytest.raises(ValueError):
            Enum('foo', 'help', unit="x")

    def test_name_cleanup_before_unit_append(self, registry):
        c = Counter('b_total', 'help', unit="total", labelnames=['l'], registry=registry)
        assert c._name == 'b_total'

    def test_concurrent(self, counter, parallel):
        class Test(ParallelLoop):
            def __init__(self):
                super().__init__(parallel)
                self.counter = counter

            def loop(self, n):
                self.counter.labels(n % self.n).inc()

            def final(self):
                for i in range(self.n):
                    assert get_sample_value(self.counter, 'c_total', {'l': str(i)}) == self.count

        Test().run()
