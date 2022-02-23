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
* Updating metrics is lock-free.
* TODO: better performance?

Users of `prometheus_flask_exporter` can import `mpmetrics.flask` instead.

## Compatibility

The following behaviors differ from `prometheus_client`:

* Labeled metrics cannot be removed or cleared.
* Info metrics are not implemented. Use `prometheus_client.Info` instead.
* Enums (StateSets) are not implemented (yet).
* Exemplars are not implemented (yet).
* Using a value of `None` for `registry` is not supported.
* `multiprocessing_mode` is not supported. Gauges have a single series with one value.

## Limitations

The following limitations apply to this library

* Only Unix is supported, and only Linux x86-64 has been tested.
* Only the `fork` start method has been tested, though the others should work.
* The python interpreter stats will only be from the current process.
* There is a soft cap of around 1000 to 2000 distinct metrics for a labeled
  metric. You can increase this cap by setting the `map_size` parameter of
  `mpmetrics.heap.Heap` to a larger value:

  ```python
  from prometheus_client import REGISTRY
  from mpmetrics.heap import Heap

  REGISTRY.heap = Heap(map_size=128 * 1024)
  ```

  Because of this cap, metric labels should not be user-generated in order to
  prevent a denial-of-service attack. For example, instead of using a "path"
  label (provided by the user), use an "endpoint" label (provided by the
  application).
