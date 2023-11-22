# SPDX-License-Identifier: LGPL-3.0-only AND Apache-2.0
# Copyright (C) 2022 Sean Anderson <seanga2@gmail.com>
# Copyright 2015 The Prometheus Authors
# Portions of this file are adapted from prometheus_client

"""Metric implementations"""

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
    """A basic collector for non-labeled metrics.

    Attributes are proxied to the underlying metric.
    """
    def __init__(self, metric, name, docs, registry, heap, kwargs):
        self._name = name
        self._docs = docs
        self._metric = metric(heap, **kwargs)
        self.__doc__ = metric.__doc__
        
        registry.register(self)

    def __getattr__(self, name):
        if name == '__getstate__':
            raise AttributeError

        try:
            return getattr(self.__dict__['_metric'], name)
        except KeyError:
            raise AttributeError

    def _family(self):
        return metrics_core.Metric(self._name, self._docs, self._metric._typ)

    def describe(self):
        """Describe the metric

        :return: An iterator yielding one metric with no samples
        :rtype: Iterator[prometheus_client.metrics_core.Metric]
        """

        yield self._family()

    def collect(self):
        """Collect samples from the metric

        :return: An iterator yielding one metric with collected samples.
        :rtype: Iterator[prometheus_client.metrics_core.Metric]
        """

        family = self._family()
        def add_sample(suffix, value, labels={}, exemplar=None):
            family.add_sample(self._name + suffix, labels, value, exemplar=exemplar)
        self._metric._sample(add_sample, self._name)
        yield family

class LabeledCollector(Struct):
    """A collector supporting labeled metrics.

    :py:func:`labels` must be called to get individual metrics.
    """
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
        self.__doc__ = metric.__doc__

        self._labelnames = tuple(labelnames)
        for label in self._labelnames:
            _validate_labelname(label)

            if hasattr(self._metric, '_reserved_labels') and label in self._metric._reserved_labels:
                raise ValueError(f"reserved label {label}")

            if getattr(self._metric, '_name_is_reserved', False) and label == name:
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
        """Return the child for the given labelset.

        All metrics can have labels, allowing grouping of related time series.
        Taking a counter as an example::

            from mpmetrics import Counter

            c = Counter('my_requests_total', 'HTTP Failures', ['method', 'endpoint'])
            c.labels('get', '/').inc()
            c.labels('post', '/submit').inc()

        Labels can also be provided as keyword arguments::

            from mpmetrics import Counter

            c = Counter('my_requests_total', 'HTTP Failures', ['method', 'endpoint'])
            c.labels(method='get', endpoint='/').inc()
            c.labels(method='post', endpoint='/submit').inc()

        See the best practices on `naming <http://prometheus.io/docs/practices/naming/>`_
        and `labels <http://prometheus.io/docs/practices/instrumentation/#use-labels>`_.
        """

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
        return metrics_core.Metric(self._name, self._docs, self._metric._typ)

    def describe(self):
        """Describe the metric

        :return: An iterator yielding one metric with no samples
        :rtype: Iterator[prometheus_client.metrics_core.Metric]
        """

        yield self._family()

    def collect(self):
        """Collect samples from the metric

        :return: An iterator yielding one metric with samples collected from each label.
        :rtype: Iterator[prometheus_client.metrics_core.Metric]
        """

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
    """A factory for creating new metrics.

    This class is used by metrics to create the appropriate collector based on the constructor
    arguments.
    """

    _heap_lock = threading.Lock()

    @classproperty
    def heap(cls):
        with cls._heap_lock:
            if not hasattr(cls, '_heap'):
                cls._heap = Heap()
            return cls._heap

    def __init__(self, metric):
        self._metric = metric
        self.__doc__ = metric.__doc__

    def __getattr__(self, name):
        return getattr(self.__dict__['_metric'], name)

    def __call__(self, name, documentation, labelnames=(), namespace="",
                 subsystem="", unit="", registry=registry.REGISTRY, **kwargs):
        """Create a new metric.

        :param str name: The name of the metric
        :param str documentation: Documentation for the metric. This will be displayed as a ``HELP``
            comment before the metric.
        :param Iterable[str] labelnames: A list of labels to be used with the metric
        :param str namespace: A global namespace for the metric. This will be prepended to `name`.
        :param str subsystem: A subsystem name for the metric. This will be prepended to `name`
            after `namespace`.
        :param str unit: The unit of measurement for the metric. This will be appended to `name`.
        :param prometheus_client.registry.CollectorRegistry registry: The registry to register this
            metric with. It will collect data from the metric.
        :param \\**kwargs: Any additional arguments are passed to the metric itself.
        :return: A new metric
        :rtype: Option[Collector, LabeledCollector]

        The name of the metric is roughly::

            name = f"{namespace}_{subsystem}_{name}_{unit}"

        with unnecessary underscores ommitted.

        If `labelnames` is truthy, then a :py:class:`LabeledCollector` for the metric will be
        returned. Otherwise a :py:class:`Collector` will be returned.
        """

        parts = []
        if namespace:
            parts.append(namespace)
        if subsystem:
            parts.append(subsystem)
        if self._metric._typ == 'counter':
            name = name.removesuffix('_total')
        if unit:
            name = name.removesuffix('_' + unit)
        parts.append(name)
        if unit:
            if self._metric._typ in ('info', 'stateset'):
                raise ValueError(f"{self._metric._typ} metrics cannot have a unit")
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
    """A Counter tracks counts of events or running totals.

    Example use cases for Counters:

    * Number of requests processed
    * Number of items that were inserted into a queue
    * Total amount of data that a system has processed

    Counters can only go up (and are reset when the process restarts). If your use case can go down,
    you should use a Gauge instead.

    An example for a Counter::

        from mpmetrics import Counter

        c = Counter('my_failures_total', 'Description of counter')
        c.inc()     # Increment by 1
        c.inc(1.6)  # Increment by given value

    There are also utilities to count exceptions raised::

        @c.count_exceptions()
        def f():
            pass

        with c.count_exceptions():
            pass

        # Count only one type of exception
        with c.count_exceptions(ValueError):
            pass

    For more information about the parameters used when creating a `Counter`, refer to
    :py:class:`~mpmetrics.metrics.CollectorFactory`.
    """

    _typ = 'counter'
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
        """Increment by the given amount."""
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
        """Count exceptions in a block of code or function.

        Can be used as a function decorator or context manager.
        Increments the counter when an exception of the given
        type is raised up out of the code.
        """

        try:
            yield
        except exception:
            self.inc()

Counter = CollectorFactory(Box[Counter])

class Gauge(Struct):
    """Gauge metric, to report instantaneous values.

    Examples of Gauges include:

    * In-progress requests
    * Number of items in a queue
    * Free memory
    * Total memory
    * Temperature

    Gauges can go both up and down::

       from mpmetrics import Gauge

       g = Gauge('my_inprogress_requests', 'Description of gauge')
       g.inc()      # Increment by 1
       g.dec(10)    # Decrement by given value
       g.set(4.2)   # Set to a given value

    There are utilities for common use cases::

       g.set_to_current_time()   # Set to current unix time

       # Increment when entered, decrement when exited.
       @g.track_inprogress()
       def f():
           pass

       with g.track_inprogress():
           pass

    A Gauge can also take its value from a callback::

       d = Gauge('data_objects', 'Number of objects')
       my_dict = {}
       d.set_function(lambda: len(my_dict))

    For more information about the parameters used when creating a `Gauge`, refer to
    :py:class:`~mpmetrics.metrics.CollectorFactory`.
    """

    _typ = 'gauge'
    _fields_ = {
        '_value': AtomicDouble,
    }

    def __init__(self, mem, **kwargs):
        super().__init__(mem)

    def inc(self, amount=1):
        """Increment by the given amount."""
        self._value.add(amount)

    def dec(self, amount=1):
        """Decrement by the given amount."""
        self._value.add(-amount)

    def set(self, amount):
        """Set to the given amount."""
        self._value.set(amount)

    def _sample(self, add_sample, name):
        add_sample('', self._value.get())

    def set_to_current_time(self):
        """Set to the current time in seconds since the Epoch."""
        self.set(time.time())

    @contextmanager
    def track_inprogress(self):
        """Track in-progress blocks of code or functions.

        Can be used as a function decorator or context manager.
        Increments the gauge when the code is entered,
        and decrements when it is exited.
        """

        self.inc()
        try:
            yield
        finally:
            self.dec()

    def time(self):
        """Time a block of code or function, and set the duration in seconds.

        Can be used as a function decorator or context manager.
        """

        return Timer(self.set)

Gauge = CollectorFactory(Box[Gauge])

class _SummaryData(Struct):
    _fields_ = {
        'sum': AtomicDouble,
        'count': AtomicUInt64,
    }

class Summary(Struct):
    """A Summary tracks the size and number of events.

    Example use cases for Summaries:

    * Response latency
    * Request size

    Example for a Summary::

        from mpmetrics import Summary

        s = Summary('request_size_bytes', 'Request size (bytes)')
        s.observe(512)  # Observe 512 (bytes)

    Example for a Summary using time::

        from mpmetrics import Summary

        REQUEST_TIME = Summary('response_latency_seconds', 'Response latency (seconds)')

        @REQUEST_TIME.time()
        def create_response(request):
          '''A dummy function'''
          time.sleep(1)

    Example for using the same Summary object as a context manager::

        with REQUEST_TIME.time():
            pass  # Logic to be timed

    For more information about the parameters used when creating a `Summary`, refer to
    :py:class:`~mpmetrics.metrics.CollectorFactory`.
    """

    _typ = 'summary'
    _reserved_labels = ('quantile',)
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
        """Observe the given amount.

        The amount is usually positive or zero. Negative values are
        accepted but prevent current versions of Prometheus from
        properly detecting counter resets in the sum of
        observations. See
        https://prometheus.io/docs/practices/histograms/#count-and-sum-of-observations
        for details.
        """

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
        """Time a block of code or function, and observe the duration in seconds.

        Can be used as a function decorator or context manager.
        """

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
    """A Histogram tracks the size and number of events in buckets.

    You can use Histograms for aggregatable calculation of quantiles.

    Example use cases:

    * Response latency
    * Request size

    Example for a Histogram::

        from mpmetrics import Histogram

        h = Histogram('request_size_bytes', 'Request size (bytes)')
        h.observe(512)  # Observe 512 (bytes)

    Example for a Histogram using time::

        from mpmetrics import Histogram

        REQUEST_TIME = Histogram('response_latency_seconds', 'Response latency (seconds)')

        @REQUEST_TIME.time()
        def create_response(request):
          '''A dummy function'''
          time.sleep(1)

    Example of using the same Histogram object as a context manager::

        with REQUEST_TIME.time():
            pass  # Logic to be timed

    For more information about the parameters used when creating a `Summary`, refer to
    :py:class:`~mpmetrics.metrics.CollectorFactory`.

    The default buckets are intended to cover a typical web/rpc request from milliseconds to
    seconds. They can be overridden by passing `buckets` keyword argument to `Histogram`.
    """

    _typ = 'histogram'
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
        Struct._setstate(self, mem, heap)
        self.thresholds = tuple(threshold.value for threshold in self._thresholds)

    def observe(self, amount, exemplar=None):
        """Observe the given amount.

        The amount is usually positive or zero. Negative values are
        accepted but prevent current versions of Prometheus from
        properly detecting counter resets in the sum of
        observations. See
        https://prometheus.io/docs/practices/histograms/#count-and-sum-of-observations
        for details.
        """

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

    def _time(self):
        """Time a block of code or function, and observe the duration in seconds.

        Can be used as a function decorator or context manager.
        """

        return Timer(self.observe)

    ns = locals()
    ns['__doc__'] = __doc__
    ns['time'] = ns['_time']
    del ns['_time']
    del ns['bucket_count']

    return type(__name__, (Struct,), ns)

_Histogram = IntType('_Histogram', _Histogram)

class _HistogramFactory:
    __doc__ = _Histogram.cls.__doc__
    _typ = 'histogram'
    _reserved_labels = ('le',)
    DEFAULT_BUCKETS = (.005, .01, .025, .05, .075, .1, .25, .5, .75, 1.0, 2.5, 5.0, 7.5, 10.0,
                       float('inf'))

    def __getattr__(self, name):
        return getattr(_Histogram[len(self.DEFAULT_BUCKETS)], name)

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
    """Enum metric, which has one selected state in a set

    Example usage::

        from mpmetrics import Enum

        e = Enum('task_state', 'Description of enum',
                 states=['starting', 'running', 'stopped'])
        e.state('running')

    The first listed state will be the default.

    For more information about the parameters used when creating a `Summary`, refer to
    :py:class:`~mpmetrics.metrics.CollectorFactory`.
    """

    _typ = 'stateset'
    _name_is_reserved = True
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
        """Select a given state."""
        self._value.set(self._states.index(state))

    def _sample(self, add_sample, name):
        val = self._value.get()
        for i, state in enumerate(self._states):
            add_sample('', int(i == val), { name: state })

Enum = CollectorFactory(Box[Enum])
