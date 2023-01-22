<!-- SPDX-License-Identifier: CC-BY-SA-3.0 -->
<!-- Copyright (C) 2022 Sean Anderson <seanga2@gmail.com> -->
# mpmetrics

mpmetrics implements metrics suitable for use with
[OpenMetrics](https://github.com/OpenObservability/OpenMetrics). It provides
multiprocess-safe replacements for
[`prometheus_client`](https://github.com/prometheus/client_python)'s `Counter`,
`Gauge`, `Summary`, and `Histogram`. To use it, just import these classes from
`mpmetrics` instead of from `prometheus_client`:

```python
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
```

Navigate to http://localhost:8000/metrics to view the results. For more
examples, look in the `examples/` directory.

## Features

* Completely thread- and process-safe.
* All operations are atomic. Metrics will never be partially updated.
* Updating metrics is lock-free on architectures with 64-bit atomics. On
  architectures with 32-bit atomics, we transparently fall back to locking
  implementations.
* Exemplars are supported, but they are locking.
* Possibly better performance than `prometheus_metrics`, but probably not a big
  contributor to overall performance.
* All `multiprocessing` start methods are supported.

Users of `prometheus_flask_exporter` can import `mpmetrics.flask` instead.

## Compatibility

The following behaviors differ from `prometheus_client`:

* Labeled metrics cannot be removed or cleared.
* Info metrics are not implemented. Use `prometheus_client.Info` instead.
* Using a value of `None` for `registry` is not supported.
* `multiprocessing_mode` is not supported. Gauges have a single series with one value.

These are unlikely to ever be addressed (except Info support) due to the
fundamental architectural changes necessary to support multiprocessing.

## Limitations

The following limitations apply to this library

* Only Unix is supported (due to use of `pthreads`). Linux and macOS are tested.
* The python interpreter stats will only be from the current process.
* The shared memory temporary files are not cleaned up properly. This is to
  keep non-`fork` start methods working (as they pickle the Heap to transfer it
  between processes

## Notes

* Metric labels should not be user-generated in order to prevent a
  denial-of-service attack due to memory exhaustion. For example, instead of
  using a "path" label (provided by the user), use an "endpoint" label
  (provided by the application).
