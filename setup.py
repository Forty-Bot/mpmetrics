#!/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2022 Sean Anderson <seanga2@gmail.com>

import os
import setuptools

setuptools.setup(
    name = 'mpmetrics',
    use_scm_version = True,
    description = "Multiprocess-safe metrics",
    long_description = open(os.path.join(os.path.dirname(__file__), 'README.md')).read(),
    long_description_content_type = 'text/markdown',
    author = 'Sean Anderson',
    author_email = 'seanga2@gmail.com',
    url = 'https://github.com/Forty-Bot/mpmetrics',
    python_requires = ">=3.9",
    packages = ['mpmetrics'],
    ext_modules = [
        setuptools.Extension(
            '_mpmetrics',
            ['_mpmetrics.c', 'atomic.c', 'lock.c'],
            extra_compile_args = [
                '-Wno-missing-braces',
            ],
        ),
    ],
    license = 'LGPL-3.0-only',
    license_files = [
        'COPYING',
        'LICENSES/*',
    ],
    setup_requires = ['setuptools_scm'],
    install_requires = [
        'prometheus_client',
    ],
    extras_require = {
        "flask": [
            'prometheus_flask_exporter',
        ],
        "tests": [
            'hypothesis',
            'pytest',
        ],
    },
)
