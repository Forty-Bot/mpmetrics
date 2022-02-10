<!-- SPDX-License-Identifier: LGPL-3.0-only -->
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

## Features

* Completely thread- and process-safe.
* All operations are atomic. Metrics will never be partially updated.
* Updating metrics is lock-free.
* TODO: better performance?

## Compatibility

The following behaviors differ from `prometheus_client`:

* Labeled metrics cannot be removed or cleared.
* Info metrics are not implemented. Use `prometheus_client.Info` instead.
* Enums (StateSets) are not implemented.
* Exemplars are not implemented.
* Using a value of `None` for `registry` is not supported.

## Limitations

The following limitations apply to this library

* Only Unix is supported, and only Linux x86-64 has been tested.
* Only the `fork` start method has been tested, though the others should work.
