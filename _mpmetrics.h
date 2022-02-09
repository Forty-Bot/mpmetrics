// SPDX-License-Identifier: LGPL-3.0-only
/*
 * Copyright (C) 2022 Sean Anderson <seanga2@gmail.com>
 */

#ifndef _MPMETRICS_H
#define _MPMETRICS_H

#define _stringify(s) #s
#define stringify(s) _stringify(s)
#define _paste(a, b) a##b
#define paste(a, b) _paste(a, b)

#ifdef __GNUC__
#define GCC_VERSION (__GNUC__ * 10000  + __GNUC_MINOR__ * 100 + \
		     __GNUC_PATCHLEVEL__)
#endif

#define maybe_unused __attribute__((__unused__))

#define NSEC_PER_SEC 1000000000

typedef struct {
	PyObject_HEAD
	Py_buffer shm;
} BufferObject;

extern PyTypeObject BufferType;

int PyType_AddSizeConstant(PyTypeObject *type, const char *name, size_t value);
int PyType_AddLLConstant(PyTypeObject *type, const char *name, long long value);
int PyType_AddULLConstant(PyTypeObject *type, const char *name,
			  unsigned long long value);
int PyType_AddDoubleConstant(PyTypeObject *type, const char *name,
			     double value);

int LockType_Add(PyObject *m);
int AtomicTypes_Add(PyObject *m);

#endif /* _MPMETRICS_H */
