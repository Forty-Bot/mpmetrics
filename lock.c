// SPDX-License-Identifier: LGPL-3.0-only
/*
 * Copyright (C) 2021-22 Sean Anderson <seanga2@gmail.com>
 */

#define PY_SSIZE_T_CLEAN
#include <Python.h>

#include <pthread.h>
#include <stdalign.h>
#include <stdbool.h>
#include <time.h>

#include "_mpmetrics.h"

static pthread_mutexattr_t mutexattr;

struct optional_timespec {
	struct timespec ts;
	bool valid;
};

typedef BufferObject LockObject;

static int Lock_init(LockObject *self, PyObject *args, PyObject *kwds)
{
	int err;

	err = BufferType.tp_init((PyObject *)self, args, kwds);
	if (err)
		return err;

	err = pthread_mutex_init(self->shm.buf, &mutexattr);
	if (err) {
		errno = err;
		PyErr_SetFromErrno(PyExc_OSError);
		BufferType.tp_clear((PyObject *)self);
		return -1;
	}

	return 0;
}

static PyObject *Lock_do_acquire(LockObject *self, bool block,
				 struct timespec *deadline)
{
	int err;

	Py_BEGIN_ALLOW_THREADS
	if (!block)
		err = pthread_mutex_trylock(self->shm.buf);
	else if (deadline)
#if defined(_POSIX_TIMEOUTS) && (_POSIX_TIMEOUTS >= 200112L)
		err = pthread_mutex_timedlock(self->shm.buf, deadline);
#else
		err = ENOTSUP;
#endif
	else
		err = pthread_mutex_lock(self->shm.buf);
	Py_END_ALLOW_THREADS

	if (!err)
		Py_RETURN_TRUE;

	if (err == EBUSY || err == ETIMEDOUT)
		Py_RETURN_FALSE;

	errno = err;
	PyErr_SetFromErrno(PyExc_OSError);

	/*
	 * We can't recover here, so just break the mutex and let the
	 * error propegate
	 */
	if (err == EOWNERDEAD)
		pthread_mutex_unlock(self->shm.buf);
	return NULL;
}

static int convert_timeout(PyObject *obj, struct optional_timespec *deadline)
{
	double timeout;

	if (obj == Py_None) {
		deadline->valid = false;
		return 1;
	}

	timeout = PyFloat_AsDouble(obj);
	if (PyErr_Occurred())
		return 0;

	if (timeout < 0.0)
		timeout = 0.0;

	if (clock_gettime(CLOCK_REALTIME, &deadline->ts) < 0) {
		PyErr_SetFromErrno(PyExc_OSError);
		return 0;
	}

	deadline->ts.tv_sec += (time_t)timeout;
	deadline->ts.tv_nsec +=
		(long)(NSEC_PER_SEC * (timeout - (time_t)timeout) + 0.5);
	deadline->ts.tv_sec += (deadline->ts.tv_nsec / NSEC_PER_SEC);
	deadline->ts.tv_nsec %= NSEC_PER_SEC;
	deadline->valid = true;
	return 1;
}

static PyObject *Lock_acquire(LockObject *self, PyObject *args, PyObject *kwds)
{
	char *keywords[] = { "block", "timeout", NULL };
	int block = true;
	struct optional_timespec deadline;

	deadline.valid = false;
	if (!PyArg_ParseTupleAndKeywords(args, kwds, "|pO&", keywords, &block,
					 convert_timeout, &deadline))
		return NULL;

	return Lock_do_acquire(self, block,
			       deadline.valid ? &deadline.ts : NULL);
}

static PyObject *Lock_release(LockObject *self, PyObject *Py_UNUSED(ignored))
{
	int err = pthread_mutex_unlock(self->shm.buf);

	if (err) {
		errno = err;
		PyErr_SetFromErrno(PyExc_OSError);
		return NULL;
	}
	Py_RETURN_NONE;
}

static PyObject *Lock_enter(LockObject *self, PyObject *Py_UNUSED(ignored))
{
	return Lock_do_acquire(self, true, NULL);
}

static PyObject *Lock_exit(LockObject *self, PyObject *const *args,
			   Py_ssize_t nargs)
{
	int err = pthread_mutex_unlock(self->shm.buf);

	if (err) {
		errno = err;
		PyErr_SetFromErrno(PyExc_OSError);
		return NULL;
	}
	Py_RETURN_NONE;
}

static PyMethodDef Lock_methods[] = {
	{
		.ml_name = "acquire",
		.ml_meth = (PyCFunction)Lock_acquire,
		.ml_flags = METH_VARARGS | METH_KEYWORDS,
		.ml_doc = "Acquire the lock",
	},
	{
		.ml_name = "release",
		.ml_meth = (PyCFunction)Lock_release,
		.ml_flags = METH_NOARGS,
		.ml_doc = "Release the lock",
	},
	{
		.ml_name = "__enter__",
		.ml_meth = (PyCFunction)Lock_enter,
		.ml_flags = METH_NOARGS,
		.ml_doc = "Enter a critical section",
	},
	{
		.ml_name = "__exit__",
		.ml_meth = (PyCFunction)Lock_exit,
		.ml_flags = METH_FASTCALL,
		.ml_doc = "Exit a critical section",
	},
	{ 0 },
};

static PyTypeObject LockType = {
	PyObject_HEAD_INIT(NULL)
	.tp_basicsize = sizeof(LockObject),
	.tp_flags = Py_TPFLAGS_DEFAULT | Py_TPFLAGS_BASETYPE,
	.tp_name = "_mpmetrics.Lock",
	.tp_doc = "Shared memory mutex lock",
	.tp_new = PyType_GenericNew,
	.tp_init = (initproc)Lock_init,
	.tp_methods = Lock_methods,
};

int LockType_Add(PyObject *m)
{
	int err;

	err = pthread_mutexattr_init(&mutexattr);
	if (err)
		goto error;

	err = pthread_mutexattr_setpshared(&mutexattr, PTHREAD_PROCESS_SHARED);
	if (err)
		goto error;

	err = pthread_mutexattr_settype(&mutexattr, PTHREAD_MUTEX_ERRORCHECK);
	if (err)
		goto error;

#if defined(_POSIX_C_SOURCE) && (_POSIX_C_SOURCE >= 200809L)
	err = pthread_mutexattr_setrobust(&mutexattr, PTHREAD_MUTEX_ROBUST);
#endif
	if (err) {
error:
		errno = err;
		PyErr_SetFromErrno(PyExc_OSError);
		return -1;
	}

	if (PyType_AddSizeConstant(&LockType, "size", sizeof(pthread_mutex_t)))
		return -1;

	if (PyType_AddSizeConstant(&LockType, "align",
				   alignof(pthread_mutex_t)))
		return -1;

	LockType.tp_base = &BufferType;
	Py_INCREF(&BufferType);
	err = PyModule_AddType(m, &LockType);
	Py_DECREF(&BufferType);
	return err;
}
