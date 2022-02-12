# SPDX-License-Identifier: LGPL-3.0-only
# Copyright (C) 2022 Sean Anderson <seanga2@gmail.com>

import prometheus_flask_exporter

from . import Gauge, Counter, Summary, Histogram

prometheus_flask_exporter.Gauge = Gauge
prometheus_flask_exporter.Counter = Counter
prometheus_flask_exporter.Summary = Summary
prometheus_flask_exporter.Histogram = Histogram

del Gauge
del Counter
del Summary
del Histogram

del prometheus_flask_exporter

from prometheus_flask_exporter import *
