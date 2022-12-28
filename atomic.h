// SPDX-License-Identifier: LGPL-3.0-only
/*
 * Copyright (C) 2021-22 Sean Anderson <seanga2@gmail.com>
 */

#ifdef DOUBLE
#define PTYPE double
#define FORMAT "d"
#define NAME AtomicDouble
#define OBJECT AtomicDouble
#define AS PyFloat_AsDouble
#define FROM PyFloat_FromDouble
#else /* DOUBLE */
#ifdef SIGNED
#define FORMAT paste(PRId, WIDTH)
#define PTYPE paste(paste(int, WIDTH), _t)
#define NAME paste(AtomicInt, WIDTH)
#define FROM PyLong_FromLongLong
#else /* SIGNED */
#define PTYPE paste(paste(uint, WIDTH), _t)
#define FORMAT paste(PRIu, WIDTH)
#define NAME paste(AtomicUInt, WIDTH)
#define FROM PyLong_FromUnsignedLongLong
#endif /* SIGNED */
#define OBJECT paste(NAME, OBJECT)
#define AS _Generic((PTYPE)0, \
	int: PyLong_AsInt, \
	long: PyLong_AsLong, \
	long long: PyLong_AsLongLong, \
	unsigned int: PyLong_AsUnsignedInt, \
	unsigned long: PyLong_AsUnsignedLong, \
	unsigned long long: PyLong_AsUnsignedLongLong)
#endif /* DOUBLE */

typedef struct {
	PyObject_HEAD
	Py_buffer shm;
} OBJECT;

#define INIT paste(NAME, _init)
static int INIT(OBJECT *self, PyObject *args, PyObject *kwds)
{
	if (BufferType.tp_init((PyObject *)self, args, kwds))
		return -1;

	atomic_init((_Atomic PTYPE *)self->shm.buf, 0);
	return 0;
}

#define GET paste(NAME, _get)
static PyObject *GET(OBJECT *self, PyObject *Py_UNUSED(ignored))
{
	PTYPE ret;

	ret = atomic_load((_Atomic PTYPE *)self->shm.buf);
	return FROM(ret);
}

#define SET paste(NAME, _set)
static PyObject *SET(OBJECT *self, PyObject *arg)
{
	PTYPE val = AS(arg);

	if (PyErr_Occurred())
		return NULL;

	atomic_store((_Atomic PTYPE *)self->shm.buf, val);

	Py_RETURN_NONE;
}

#define ADD paste(NAME, _add)
static PyObject *ADD(OBJECT *self, PyObject *args, PyObject *kwds)
{
	PTYPE amount, old;

	char *keywords[] = { "amount", "raise_on_overflow", NULL };
	int raise = 1;
	PyObject *amount_obj;

	if (!PyArg_ParseTupleAndKeywords(args, kwds, "O|p", keywords,
					 &amount_obj, &raise))
		return NULL;

	amount = AS(amount_obj);
	if (PyErr_Occurred())
		return NULL;

#ifdef DOUBLE
	PTYPE new;

	do {
		old = atomic_load((_Atomic PTYPE *)self->shm.buf);
		new = old + amount;
	} while (!atomic_compare_exchange_weak((_Atomic PTYPE *)self->shm.buf,
					       &old, new));
#else
	PTYPE dummy;

	old = atomic_fetch_add((_Atomic PTYPE *)self->shm.buf, amount);
	/*
	 * __builtin_add_overflow_p is gcc-specific, so just use
	 * __builtin_add_overflow and ignore the result 
	 */
	if (raise && __builtin_add_overflow(old, amount, &dummy)) {
		PyErr_Format(PyExc_OverflowError,
			     "%" FORMAT " + %" FORMAT " too large to fit in " stringify(PTYPE),
			     amount, old);
		return NULL;	
	}
#endif
	return FROM(old);
}

#define METHODS paste(NAME, _methods)
static PyMethodDef METHODS[] = {
	{ 
		.ml_name = "get",
		.ml_meth = (PyCFunction)GET,
		.ml_flags = METH_NOARGS,
		.ml_doc = "Get the current value",
	},
	{
		.ml_name = "set",
		.ml_meth = (PyCFunction)SET,
		.ml_flags = METH_O,
		.ml_doc = "Set the current value",
	},
	{
		.ml_name = "add",
		.ml_meth = (PyCFunction)ADD,
		.ml_flags = METH_VARARGS | METH_KEYWORDS,
		.ml_doc = "Add a number to the value",
	},
	{ 0 },
};

#define TYPE paste(NAME, Type)
static PyTypeObject TYPE = {
	PyObject_HEAD_INIT(NULL)
	.tp_basicsize = sizeof(OBJECT),
	.tp_flags = Py_TPFLAGS_DEFAULT | Py_TPFLAGS_BASETYPE,
	.tp_name = "_mpmetrics." stringify(NAME),
#ifdef DOUBLE
	.tp_doc = "Atomic " stringify(PTYPE),
#else
	.tp_doc = "Atomic " stringify(WIDTH) "-bit integer",
#endif
	.tp_new = PyType_GenericNew,
	.tp_init = (initproc)INIT,
	.tp_methods = METHODS,
};

#define TYPE_ADD paste(TYPE, _Add)
static int TYPE_ADD(PyObject *m)
{
	int ret;

	if (!atomic_is_lock_free((_Atomic PTYPE *)NULL)) {
		int ret;

		Py_INCREF(Py_None);
		ret = PyModule_AddObject(m, stringify(NAME), Py_None);
		Py_DECREF(Py_None);
		return ret;
	}

	if (PyType_AddSizeConstant(&TYPE, "size", sizeof(PTYPE)))
		return -1;

/* https://gcc.gnu.org/bugzilla/show_bug.cgi?id=65146 */
#if defined(GCC_VERSION) && GCC_VERSION < 110100
	if (PyType_AddSizeConstant(&TYPE, "align", sizeof(PTYPE)))
#else
	if (PyType_AddSizeConstant(&TYPE, "align", alignof(PTYPE)))
#endif
		return -1;

#ifndef DOUBLE
#ifdef SIGNED
	if (PyType_AddLLConstant(&TYPE, "min", paste(paste(INT, WIDTH), _MIN)))
		return -1;

	if (PyType_AddLLConstant(&TYPE, "max", paste(paste(INT, WIDTH), _MAX)))
		return -1;
#else
	if (PyType_AddULLConstant(&TYPE, "min", 0))
		return -1;

	if (PyType_AddULLConstant(&TYPE, "max", paste(paste(UINT, WIDTH), _MAX)))
		return -1;
#endif
#endif

	TYPE.tp_base = &BufferType;
	Py_INCREF(&BufferType);
	ret = PyModule_AddType(m, &TYPE);
	Py_DECREF(&BufferType);
	return ret;
}

#undef INIT
#undef GET
#undef SET
#undef ADD
#undef METHODS
#undef TYPE
#undef TYPE_ADD

#undef PTYPE
#undef FORMAT
#undef NAME
#undef OBJECT
#undef AS
#undef FROM
