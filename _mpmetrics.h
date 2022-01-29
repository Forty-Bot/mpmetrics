// SPDX-License-Identifier: LGPL-3.0-only
/*
 * Copyright (C) 2022 Sean Anderson <seanga2@gmail.com>
 */

#ifndef _MPMETRICS_H
#define _MPMETRICS_H

#define NSEC_PER_SEC 1000000000

typedef struct {
	PyObject_HEAD
	Py_buffer shm;
} BufferObject;

extern PyTypeObject BufferType;

int PyType_AddSizeConstant(PyTypeObject *type, const char *name, size_t value);

int LockType_Add(PyObject *m);

#endif /* _MPMETRICS_H */
