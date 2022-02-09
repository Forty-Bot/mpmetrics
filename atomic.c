// SPDX-License-Identifier: LGPL-3.0-only
/*
 * Copyright (C) 2021 Sean Anderson <seanga2@gmail.com>
 */

#define PY_SSIZE_T_CLEAN
#include <Python.h>

#ifndef _GNU_SOURCE
#define _GNU_SOURCE
#endif
#include <pthread.h>
#include <stdalign.h>
#include <stdatomic.h>
#include <stdbool.h>
#include <stdint.h>
#include <sys/mman.h>

#include "_mpmetrics.h"

static maybe_unused int PyLong_AsInt(PyObject *obj)
{
	long value = PyLong_AsLong(obj);

	if (PyErr_Occurred())
		return 0;

	if (value > INT_MAX || value < INT_MIN) {
		PyErr_Format(PyExc_OverflowError,
			     "%ld too large to convert to int", value);
		return 0;
	}

	return value;
}

static maybe_unused unsigned int PyLong_AsUnsignedInt(PyObject *obj)
{
	unsigned long value = PyLong_AsUnsignedLong(obj);

	if (PyErr_Occurred())
		return 0;

	if (value > UINT_MAX) {
		PyErr_Format(PyExc_OverflowError,
			     "%lu too large to convert to int", value);
		return 0;
	}

	return value;
}

/* my apologies */

#define WIDTH 32
#include "atomic.h"
#undef WIDTH

#define WIDTH 64
#include "atomic.h"
#undef WIDTH

#define SIGNED
#define WIDTH 32
#include "atomic.h"
#undef WIDTH

#define WIDTH 64
#include "atomic.h"
#undef WIDTH
#undef SIGNED

#define DOUBLE
#include "atomic.h"
#undef DOUBLE

int AtomicTypes_Add(PyObject *m)
{
	if (AtomicInt32Type_Add(m))
		return -1;

	if (AtomicInt64Type_Add(m))
		return -1;

	if (AtomicUInt32Type_Add(m))
		return -1;

	if (AtomicUInt64Type_Add(m))
		return -1;

	if (AtomicDoubleType_Add(m))
		return -1;

	return 0;
}
