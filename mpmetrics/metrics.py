# SPDX-License-Identifier: LGPL-3.0-only AND Apache-2.0
# Copyright (C) 2022 Sean Anderson <seanga2@gmail.com>
# Copyright 2015 The Prometheus Authors
# Portions of this file are adapted from prometheus_client

import bisect
from contextlib import contextmanager
import itertools
import sys
import threading
import time

from prometheus_client import metrics, metrics_core, registry, samples

import _mpmetrics
from .atomic import AtomicUInt64, AtomicDouble
from .generics import IntType
from .heap import Heap
from .types import Box, Dict, Double, Array, List, Struct, UInt64
from .util import classproperty, genmask

@contextmanager
def Timer(callback):
    now = time.perf_counter()
    yield
    callback(max(time.perf_counter() - now, 0))

def _validate_labelname(label):
    if not metrics_core.METRIC_LABEL_NAME_RE.match(label):
        raise ValueError(f"invalid label {label}")

    if metrics_core.RESERVED_METRIC_LABEL_NAME_RE.match(label):
        raise ValueError(f"reserved label {label}")

def _validate_exemplar(exemplar):
    code_points = 0
    for k, v in exemplar.items():
        _validate_labelname(k)
        code_points += len(k)
        code_points += len(v)

    if code_points > 128:
        raise ValueError("exemplar too long ({code_points} code points)")

class Collector:
    def __init__(self, metric, name, docs, registry, heap, kwargs):
        self._name = name
        self._docs = docs
        self._metric = metric(heap, **kwargs)
        
        registry.register(self)

    def __getattr__(self, name):
        if name == '__getstate__':
            raise AttributeError

        try:
            return getattr(self.__dict__['_metric'], name)
        except KeyError:
            raise AttributeError

    def _family(self):
        return metrics_core.Metric(self._name, self._docs, self._metric.typ)

    def describe(self):
        yield self._family()

    def collect(self):
        family = self._family()
        def add_sample(suffix, value, labels={}, exemplar=None):
            family.add_sample(self._name + suffix, labels, value, exemplar=exemplar)
        self._metric._sample(add_sample, self._name)
        yield family

class LabeledCollector(Struct):
    _fields_ = {
        '_shared_lock': _mpmetrics.Lock,
        '_metrics': Dict,
    }

    def __init__(self, mem, metric, name, docs, labelnames, registry, kwargs, heap):
        super().__init__(mem, heap=heap)

        self._metric = metric
        self._name = name
        self._docs = docs
        self._kwargs = kwargs
        self._heap = heap

        self._labelnames = tuple(labelnames)
        for label in self._labelnames:
            _validate_labelname(label)

            if hasattr(self._metric, 'reserved_labels') and label in self._metric.reserved_labels:
                raise ValueError(f"reserved label {label}")

            if getattr(self._metric, 'name_is_reserved', False) and label == name:
                raise ValueError(f"reserved label {label}")

        self._lock = threading.Lock()
        self._cache = dict()
        registry.register(self)

    def _getstate(self):
        return {
            'metric': self._metric,
            'name': self._name,
            'docs': self._docs,
            'kwargs': self._kwargs,
            'labelnames': self._labelnames,
        }

    def _setstate(self, mem, metric, name, docs, kwargs, labelnames, heap, **others):
        super()._setstate(mem, heap)
        self._metric = metric
        self._name = name
        self._docs = docs
        self._kwargs = kwargs
        self._heap = heap
        self._labelnames = labelnames
        self._lock = threading.Lock()
        self._cache = dict()

    def _label_values(self, values, labels):
        if values and labels:
            raise ValueError("can't pass both *args and **kwargs")

        if labels:
            if sorted(labels) != sorted(self._labelnames):
                raise ValueError("incorrect label names")
            values = (labels[label] for label in self._labelnames)
        else:
            if len(values) != len(self._labelnames):
                raise ValueError("incorrect label count")
        return tuple(sys.intern(str(label)) for label in values)

    def labels(self, *values, **labels):
        values = self._label_values(values, labels)

        with self._lock:
            metric = self._cache.get(values)
            if not metric:
                with self._shared_lock:
                    metric = self._metrics.get(values)
                    if not metric:
                        metric = self._metric(self._heap, **self._kwargs)
                        self._metrics[values] = metric
                self._cache[values] = metric
            return metric

    def _family(self):
        return metrics_core.Metric(self._name, self._docs, self._metric.typ)

    def describe(self):
        yield self._family()

    def collect(self):
        family = self._family()
        with self._lock:
            with self._shared_lock:
                for values, metric in self._metrics.items():
                    if values not in self._cache:
                        self._cache[values] = metric
            metrics = self._cache

        for labelvalues, metric in metrics.items():
            metric_labels = dict(zip(self._labelnames, labelvalues))
            def add_sample(suffix, value, labels={}, exemplar=None):
                family.add_sample(self._name + suffix, metric_labels | labels, value,
                                  exemplar=exemplar)
            metric._sample(add_sample, self._name)
        yield family

class CollectorFactory:
    _heap_lock = threading.Lock()

    @classproperty
    def heap(cls):
        with cls._heap_lock:
            if not hasattr(cls, '_heap'):
                cls._heap = Heap()
            return cls._heap

    def __init__(self, metric):
        self._metric = metric

    def __getattr__(self, name):
        return getattr(self.__dict__['_metric'], name)

    def __call__(self, name, documentation, labelnames=(), namespace="",
                 subsystem="", unit="", registry=registry.REGISTRY, **kwargs):

        parts = []
        if namespace:
            parts.append(namespace)
        if subsystem:
            parts.append(subsystem)
        if self._metric.typ == 'counter':
            name = name.removesuffix('_total')
        if unit:
            name = name.removesuffix('_' + unit)
        parts.append(name)
        if unit:
            if self._metric.typ in ('info', 'stateset'):
                raise ValueError(f"{self._metric.typ} metrics cannot have a unit")
            parts.append(unit)

        name = '_'.join(parts)
        if not metrics_core.METRIC_NAME_RE.match(name):
            raise ValueError(f"invalid metric name {name}")

        heap = getattr(registry, 'heap', self.heap)

        if labelnames:
            return Box[LabeledCollector](heap, self._metric, name, documentation, labelnames,
                                         registry, kwargs)
        return Collector(self._metric, name, documentation, registry, heap, kwargs)

class Counter(Struct):
    typ = 'counter'
    _fields_ = {
        '_lock': _mpmetrics.Lock,
        '_total': AtomicUInt64,
        '_created': Double,
        '_exemplar_amount': UInt64,
        '_exemplar_timestamp': Double,
        '_exemplar_labels': Dict,
    }

    def __init__(self, mem, heap, **kwargs):
        super().__init__(mem, heap)
        self._created.value = time.time()

    def inc(self, amount=1, exemplar=None):
        if amount < 0:
            raise ValueError("amount must be positive")

        if exemplar is not None:
            _validate_exemplar(exemplar)
   
        self._total.add(amount)
        if exemplar is not None:
            with self._lock:
                self._exemplar_amount.value = amount
                self._exemplar_timestamp.value = time.time()
                self._exemplar_labels.clear()
                self._exemplar_labels |= exemplar

    def _sample(self, add_sample, name):
        with self._lock:
            timestamp = self._exemplar_timestamp.value
            if timestamp:
                amount = self._exemplar_amount.value
                labels = self._exemplar_labels.copy()
        add_sample('_total', self._total.get(),
                   exemplar=samples.Exemplar(labels, amount, timestamp) if timestamp else None)
        add_sample('_created', self._created.value)

    @contextmanager
    def count_exceptions(self, exception=Exception):
        try:
            yield
        except exception:
            self.inc()

Counter = CollectorFactory(Box[Counter])

class Gauge(Struct):
    typ = 'gauge'
    _fields_ = {
        '_value': AtomicDouble,
    }

    def __init__(self, mem, **kwargs):
        super().__init__(mem)

    def inc(self, amount=1):
        self._value.add(amount)

    def dec(self, amount=1):
        self._value.add(-amount)

    def set(self, amount):
        self._value.set(amount)

    def _sample(self, add_sample, name):
        add_sample('', self._value.get())

    def set_to_current_time(self):
        self.set(time.time())

    @contextmanager
    def track_inprogress(self):
        self.inc()
        try:
            yield
        finally:
            self.dec()

    def time(self):
        return Timer(self.set)

Gauge = CollectorFactory(Box[Gauge])

class _SummaryData(Struct):
    _fields_ = {
        'sum': AtomicDouble,
        'count': AtomicUInt64,
    }

class Summary(Struct):
    typ = 'summary'
    reserved_labels = ('quantile',)
    _fields_ = {
        '_lock': _mpmetrics.Lock,
        '_data': Array[_SummaryData, 2],
        '_count': AtomicUInt64,
        '_created': Double,
    }

    def __init__(self, mem, **kwargs):
        super().__init__(mem)
        self._created.value = time.time()

    def observe(self, amount):
        data = self._data[self._count.add(1) >> 63]
        data.sum.add(amount)
        data.count.add(1)

    def _sample(self, add_sample, name):
        with self._lock:
            count = self._count.add(1 << 63, raise_on_overflow=False)
            hot = self._data[~count >> 63]
            cold = self._data[count >> 63]
            count &= genmask(62, 0)

            while cold.count.get() != count:
                time.sleep(0)

            sum = cold.sum.get()
            hot.count.add(count)
            hot.sum.add(sum)
            cold.count.set(0)
            cold.sum.set(0)

        add_sample('_count', count)
        add_sample('_sum', sum)
        add_sample('_created', self._created.value)

    def time(self):
        return Timer(self.observe)

Summary = CollectorFactory(Box[Summary])

def _HistogramData(__name__, bucket_count):
    _fields_ = {
        'buckets': Array[AtomicUInt64, bucket_count],
        'sum': AtomicDouble,
        'count': AtomicUInt64,
    }

    ns = locals()
    del ns['bucket_count']
    return type(__name__, (Struct,), ns)

_HistogramData = IntType('_HistogramData', _HistogramData)

def _Histogram(__name__, bucket_count):
    typ = 'histogram'
    _fields_ = {
        '_thresholds': Array[Double, bucket_count],
        '_lock': _mpmetrics.Lock,
        '_data': Array[_HistogramData[bucket_count], 2],
        '_count': AtomicUInt64,
        '_created': Double,
        '_exemplars': List,
    }

    def __init__(self, mem, thresholds, heap, **kwargs):
        Struct.__init__(self, mem, heap)
        assert len(thresholds) == bucket_count
        self.thresholds = thresholds
        for threshold, initial in zip(self._thresholds, thresholds):
            threshold.value = initial
            self._exemplars.append(None)
        self._created.value = time.time()

    def _setstate(self, mem, heap):
        Struct._setstate(self, mem)
        self.thresholds = tuple(threshold.value for threshold in self._thresholds)

    def observe(self, amount, exemplar=None):
        if exemplar is not None:
            _validate_exemplar(exemplar)

        i = bisect.bisect_left(self.thresholds, amount)

        data = self._data[self._count.add(1) >> 63]
        data.buckets[i].add(1)
        data.sum.add(amount)
        data.count.add(1)
        if exemplar:
            with self._lock:
                self._exemplars[i] = (exemplar, amount, time.time())

    def _sample(self, add_sample, name):
        with self._lock:
            count = self._count.add(1 << 63, raise_on_overflow=False)
            hot = self._data[~count >> 63]
            cold = self._data[count >> 63]
            count &= genmask(62, 0)

            while cold.count.get() != count:
                time.sleep(0)

            buckets = [bucket.get() for bucket in cold.buckets]
            sum = cold.sum.get()
            exemplars = list(self._exemplars)

            for i, bucket in enumerate(buckets):
                hot.buckets[i].add(bucket)
            hot.sum.add(sum)
            hot.count.add(count)

            for bucket in cold.buckets:
                bucket.set(0)
            cold.sum.set(0)
            cold.count.set(0)

        for val, le, exemplar in zip(itertools.accumulate(buckets), self.thresholds, exemplars):
            add_sample('_bucket', val, { 'le': str(le) },
                       samples.Exemplar(*exemplar) if exemplar else None)
        add_sample('_sum', sum)
        add_sample('_count', count)
        add_sample('_created', self._created.value)

    ns = locals()
    ns['time'] = lambda self: Timer(self.observe)
    del ns['bucket_count']

    return type(__name__, (Struct,), ns)

_Histogram = IntType('_Histogram', _Histogram)

class _HistogramFactory:
    typ = 'histogram'
    reserved_labels = ('le',)
    DEFAULT_BUCKETS = (.005, .01, .025, .05, .075, .1, .25, .5, .75, 1.0, 2.5, 5.0, 7.5, 10.0,
                       float('inf'))

    def __call__(self, heap, buckets=DEFAULT_BUCKETS, **kwargs):
        thresholds = [float(b) for b in buckets]
        if thresholds != sorted(thresholds):
            raise ValueError('thresholds not in sorted order')
        if thresholds and thresholds[-1] != float('inf'):
            thresholds.append(float('inf'))
        if len(thresholds) < 2:
            raise ValueError('must have at least two thresholds')
        thresholds = tuple(thresholds)

        histogram = Box[_Histogram[len(thresholds)]]
        return histogram(heap, thresholds=thresholds, **kwargs)

Histogram = CollectorFactory(_HistogramFactory())

class Enum(Struct):
    typ = 'stateset'
    name_is_reserved = True
    _fields_ = {
        '_value': AtomicUInt64,
    }

    def __init__(self, mem, states, **kwargs):
        super().__init__(mem)
        self._states = states

    def _getstate(self):
        return { 'states': self._states }

    def _setstate(self, mem, heap, states):
        super()._setstate(mem, heap)
        self._states = states

    def state(self, state):
        self._value.set(self._states.index(state))

    def _sample(self, add_sample, name):
        val = self._value.get()
        for i, state in enumerate(self._states):
            add_sample('', int(i == val), { name: state })

Enum = CollectorFactory(Box[Enum])
