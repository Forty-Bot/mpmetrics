mpmetrics
=========

.. automodule:: mpmetrics

.. autodata:: mpmetrics.Counter

        .. automethod:: mpmetrics.Counter.inc
        .. automethod:: mpmetrics.Counter.count_exceptions

.. autodata:: mpmetrics.Gauge

        .. automethod:: mpmetrics.Gauge.inc
        .. automethod:: mpmetrics.Gauge.dec
        .. automethod:: mpmetrics.Gauge.set
        .. automethod:: mpmetrics.Gauge.set_to_current_time
        .. automethod:: mpmetrics.Gauge.track_inprogress
        .. automethod:: mpmetrics.Gauge.time

.. autodata:: mpmetrics.Summary

        .. automethod:: mpmetrics.Summary.observe
        .. automethod:: mpmetrics.Summary.time

.. autodata:: mpmetrics.Histogram

        .. automethod:: mpmetrics.Histogram.observe
        .. automethod:: mpmetrics.Histogram.time

.. autodata:: mpmetrics.Enum

        .. automethod:: mpmetrics.Enum.state

mpmetrics.metrics
-----------------

.. automodule:: mpmetrics.metrics

        .. autoclass:: mpmetrics.metrics.CollectorFactory
                :members:
                :special-members: __call__

        .. autoclass:: mpmetrics.metrics.Collector
                :members:

        .. autoclass:: mpmetrics.metrics.LabeledCollector
                :members:

mpmetrics.flask
---------------

.. automodule:: mpmetrics.flask
