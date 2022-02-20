<!-- SPDX-License-Identifier: CC-BY-SA-3.0 -->
<!-- Copyright (C) 2022 Sean Anderson <seanga2@gmail.com> -->
# Examples

This directory contains several examples ready to run. In order to import
`mpmetrics` correctly, you will need to either

* Run these examples from the top-level directory
* Install `mpmetrics` (with pip, etc.)

## `readme.py`

This is the same file as the example in the top-level `README.md`, broken out
for convenience. Run it like

```
$ examples/readme.py
```

Navigate to http://localhost:8000/metrics to view the metrics.

## `flask_server.py` and `flask_client.py`

These files implement a flask server and a dummy client to generate requests.
Metrics for the server are implemented using
`mpmetrics.flask.PrometheusMetrics`. Run the server like

```
$ examples/flask_server.py
```

Then, from a separate terminal, run the client

```
$ examples/flask_client.py
```

In the server's terminal, you should see requests being made. Navigate to
http://localhost:8000/metrics to view the metrics.

### uwsgi

You can also run the server using uwsgi which will use multiple processes:

```
$ uwsgi --http localhost:8000 --plugins python --module examples.flask_server:app \
        --processes 4 --threads 2
```
