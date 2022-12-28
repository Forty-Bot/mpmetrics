// SPDX-License-Identifier: LGPL-3.0-only
/*
 * Copyright (C) 2021-22 Sean Anderson <seanga2@gmail.com>
 */

#define PY_SSIZE_T_CLEAN
#include <Python.h>
#include <structmember.h>

#include "_mpmetrics.h"

static int Buffer_init(BufferObject *self, PyObject *args, PyObject *kwds)
{
	PyObject *size_obj;
	size_t size;

	if (!PyArg_ParseTuple(args, "w*", &self->shm))
		return -1;

	size_obj = PyObject_GetAttrString((PyObject *)self, "size");
	if (!size_obj)
		goto error;

	size = PyLong_AsSize_t(size_obj);
	Py_DECREF(size_obj);
	if (PyErr_Occurred())
		goto error;

	if ((size_t)self->shm.len < size) {
		PyErr_Format(PyExc_ValueError,
			     "shared memory (%zd bytes) too small; must be at least %zu bytes",
			     self->shm.len, size);
		goto error;
	}

	return 0;

error:
	PyBuffer_Release(&self->shm);
	return -1;
}

static int Buffer_traverse(BufferObject *self, visitproc visit, void *arg)
{
	Py_VISIT(self->shm.obj);
	return 0;
}

static int Buffer_clear(BufferObject *self)
{
	PyBuffer_Release(&self->shm);
	return 0;
}

static void Buffer_dealloc(BufferObject *self)
{
	Buffer_clear(self);
	Py_TYPE(self)->tp_free((PyObject *)self);
}

static PyObject *Buffer_setstate(BufferObject *self, PyObject *args,
				 PyObject *kwds)
{
	if (Buffer_init(self, args, kwds))
		return NULL;
	Py_RETURN_NONE;
}

static PyMethodDef Buffer_methods[] = {
	{
		.ml_name = "_setstate",
		.ml_meth = (PyCFunction)Buffer_setstate,
		.ml_flags = METH_VARARGS | METH_KEYWORDS,
	},
	{ 0 },
};


PyTypeObject BufferType = {
	PyObject_HEAD_INIT(NULL)
	.tp_basicsize = sizeof(BufferObject),
	.tp_flags = Py_TPFLAGS_DEFAULT | Py_TPFLAGS_BASETYPE |
		    Py_TPFLAGS_HAVE_GC,
	.tp_name = "_mpmetrics.Buffer",
	.tp_doc = "Shared memory buffer base class",
	.tp_new = PyType_GenericNew,
	.tp_init = (initproc)Buffer_init,
	.tp_dealloc = (destructor)Buffer_dealloc,
	.tp_traverse = (traverseproc)Buffer_traverse,
	.tp_clear = (inquiry)Buffer_clear,
	.tp_methods = Buffer_methods,
};

static int PyType_AddConstant(PyTypeObject *type, const char *name,
			      PyObject *obj)
{
	int ret;

	if (!type->tp_dict) {
		type->tp_dict = PyDict_New();
		if (!type->tp_dict) {
			Py_DECREF(obj);
			return -1;
		}
	}

	ret = PyDict_SetItemString(type->tp_dict, name, obj);
	Py_DECREF(obj);
	return ret;
}

int PyType_AddSizeConstant(PyTypeObject *type, const char *name, size_t value)
{
	PyObject *obj = PyLong_FromSize_t(value);

	if (!obj)
		return -1;

	return PyType_AddConstant(type, name, obj);
}

int PyType_AddLLConstant(PyTypeObject *type, const char *name, long long value)
{
	PyObject *obj = PyLong_FromLongLong(value);

	if (!obj)
		return -1;

	return PyType_AddConstant(type, name, obj);
}

int PyType_AddULLConstant(PyTypeObject *type, const char *name,
			  unsigned long long value)
{
	PyObject *obj = PyLong_FromUnsignedLongLong(value);

	if (!obj)
		return -1;

	return PyType_AddConstant(type, name, obj);
}

int PyType_AddDoubleConstant(PyTypeObject *type, const char *name,
			     double value)
{
	PyObject *obj = PyLong_FromDouble(value);

	if (!obj)
		return -1;

	return PyType_AddConstant(type, name, obj);
}

static PyModuleDef module = {
	PyModuleDef_HEAD_INIT,
	.m_name = "_mpmetrics",
	.m_doc = "C helpers for multiprocess-safe metrics",
	.m_size = -1,
};

PyMODINIT_FUNC PyInit__mpmetrics(void)
{
	PyObject *m;

	m = PyModule_Create(&module);
	if (!m)
		return NULL;

	if (PyModule_AddType(m, &BufferType))
		goto error;

	if (LockType_Add(m))
		goto error;

	if (AtomicTypes_Add(m)) {
error:
		Py_DECREF(m);
		return NULL;
	}

	return m;
}
