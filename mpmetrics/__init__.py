# SPDX-License-Identifier: LGPL-3.0-only
# Copyright (C) 2022 Sean Anderson <seanga2@gmail.com>

"""multiprocess-safe metrics

mpmetrics implements metrics suitable for use with OpenMetrics. It provides
multiprocess-safe replacements for prometheus_client's Counter, Gauge, Summary,
Histogram, and Enum. To use it, just import these classes from this module
instead of from prometheus_client.
"""

from .metrics import Counter, Gauge, Summary, Histogram, Enum

__all__ = ('Counter', 'Gauge', 'Summary', 'Histogram', 'Enum')
