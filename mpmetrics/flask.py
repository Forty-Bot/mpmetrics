# SPDX-License-Identifier: LGPL-3.0-only
# Copyright (C) 2022 Sean Anderson <seanga2@gmail.com>

"""Import this module to monkey-patch `prometheus_flask_exporter` to use mpmetrics' metrics."""

import prometheus_flask_exporter

from . import Counter, Gauge, Summary, Histogram, Enum

prometheus_flask_exporter.Gauge = Gauge
prometheus_flask_exporter.Counter = Counter
prometheus_flask_exporter.Summary = Summary
prometheus_flask_exporter.Histogram = Histogram
prometheus_flask_exporter.Enum = Enum

del Gauge
del Counter
del Summary
del Histogram
del Enum

del prometheus_flask_exporter

from prometheus_flask_exporter import *
