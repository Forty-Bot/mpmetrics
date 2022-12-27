#!/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2022 Sean Anderson <seanga2@gmail.com>

import os
import setuptools
import setuptools.command.build_ext

class build_ext(setuptools.command.build_ext.build_ext):
    def build_extension(self, ext):
        if self.compiler.compiler_type == 'msvc':
            ext.extra_compile_args = ["/std:c11"]
        else:
            ext.extra_compile_args = ["-Wno-missing-braces"]
        super().build_extension(ext)

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
    cmdclass = {'build_ext': build_ext},
    ext_modules = [
        setuptools.Extension(
            '_mpmetrics',
            ['_mpmetrics.c', 'atomic.c', 'lock.c'],
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
            'flask',
            'freezegun',
            'hypothesis',
            'prometheus_flask_exporter',
            'pytest',
        ],
    },
)
