mpmetrics
=========

mpmetrics implements metrics suitable for use with `OpenMetrics
<https://github.com/OpenObservability/OpenMetrics>`_. It provides
multiprocess-safe replacements for `prometheus_client
<https://github.com/prometheus/client_python>`_'s `Counter`,
`Gauge`, `Summary`, `Histogram`, and `Enum`. To use it, just import
these classes from `mpmetrics` instead of from `prometheus_client`::

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

        # Create function for subprocess
        def generate_requests():
            while True:
                process_request(random.random())

        if __name__ == '__main__':
            # Start up the server to expose the metrics.
            start_http_server(8000)
            # Generate some requests from two processes
            multiprocessing.Process(target=generate_requests).start()
            generate_requests()

Navigate to http://localhost:8000/metrics to view the results. For
more examples, look in the ``examples/`` directory.

.. toctree::
        :maxdepth: 2
        :caption: Contents:

        mpmetrics
        internals

Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
