# SPDX-License-Identifier: LGPL-3.0-only
# Copyright (C) 2022 Sean Anderson <seanga2@gmail.com>

"""Helpers for pickling polymorphic classes."""

import importlib
import itertools

def saveattr(get):
    """Save the result of `__getattr__`.

    :param get: A `__getattr__` implementation

    Wrap `get` and save the result with `setattr`.
    """
    def wrapped(self, name):
        attr = get(self, name)
        setattr(self, name, attr)
        return attr
    return wrapped

class ObjectType:
    """Helper for classes polymorphic over classes.

    This is a helper class to allow classes which are polymorphic over python
    classes to be pickled. For example::

        import pickle
        from mpmetrics.generics import ObjectType

        def MyClass(__name__, cls):
            return type(__name__, (), locals())

        MyClass = ObjectType('MyClass', MyClass)
        assert MyClass[int].cls is int
        assert pickle.loads(pickle.dumps(MyClass[int]())).cls is int
    """

    class Attr:
        def __init__(self, name, cls, obj, nesting=1):
            self.name = name
            self.cls = cls
            self.obj = obj
            self.nesting = nesting

        @saveattr
        def __getattr__(self, name):
            nesting = self.nesting + (name == '<') - (name == '>')
            if name == '>' and not nesting:
                return self.cls(self.name + '.' + self.obj.__qualname__ + '.>', self.obj)
            else:
                return type(self)(self.name, self.cls, getattr(self.obj, name), nesting)

    class Module:
        def __init__(self, name, cls, parent=None):
            self.name = name
            self.cls = cls
            self.parent = parent

        @saveattr
        def __getattr__(self, name):
            try:
                if self.parent:
                    module = self.parent.__name__ + '.' + name
                else:
                    module = name
                return type(self)(self.name, self.cls, importlib.import_module(module))
            except ModuleNotFoundError:
                if self.parent:
                    prefix = self.name + '.' + self.parent.__name__
                else:
                    prefix = self.name
                return ObjectType.Attr(prefix, self.cls, getattr(self.parent, name))

    def __init__(self, name, cls):
        self.__qualname__ = name
        self.__doc__ = cls.__doc__
        setattr(self, '<', self.Module(name + '.<', cls))

    def __getitem__(self, cls):
        parent = getattr(self, '<')
        for subpath in itertools.chain(cls.__module__.split('.'), cls.__qualname__.split('.')):
            parent = getattr(parent, subpath)
        return getattr(parent, '>')

class IntType:
    """Helper for classes polymorphic over integers.

    This is a helper class to allow classes which are polymorphic over ints
    to be pickled. For example::

        import pickle
        from mpmetrics.generics import IntType

        def MyClass(__name__, x):
            return type(__name__, (), locals())

        MyClass = IntType('MyClass', MyClass)
        assert MyClass[5].x == 5
        assert pickle.loads(pickle.dumps(MyClass[5]())).x == 5
    """

    def __init__(self, name, cls):
        self.__qualname__ = name
        self.__doc__ = cls.__doc__
        self.name = name
        self.cls = cls

    @saveattr
    def __getattr__(self, attr):
        return self.cls(self.name + '.' + attr, int(attr))

    def __getitem__(self, n):
        return getattr(self, repr(n))

class FloatType:
    """Helper for classes polymorphic over floats.

    This is a helper class to allow classes which are polymorphic over floats
    to be pickled. For example::

        import pickle
        from mpmetrics.generics import FloatType

        def MyClass(__name__, x):
            return type(__name__, (), locals())

        MyClass = FloatType('MyClass', MyClass)
        assert MyClass[2.7].x == 2.7
        assert pickle.loads(pickle.dumps(MyClass[2.7]())).x == 2.7
    """

    def __init__(self, name, cls):
        self.__qualname__ = name
        self.__doc__ = cls.__doc__
        self.name = name
        self.cls = cls

    @saveattr
    def __getattr__(self, attr):
        return self.cls(self.name + '.' + attr, float(attr.replace('_', '.')))

    def __getitem__(self, n):
        return getattr(self, repr(n).replace('.', '_'))


class ProductType:
    """Helper to combine other types.

    This is a helper class to allow classes which are polymorphic over multiple
    types to be pickled. For example::

        import pickle
        from mpmetrics.generics import IntType, ObjectType, ProductType

        def MyClass(__name__, cls, x):
            return type(__name__, (), locals())

        MyClass = ProductType('MyClass', MyClass, (ObjectType, IntType))
        assert MyClass[int, 5].cls is int
        assert MyClass[int, 5].x == 5
        assert pickle.loads(pickle.dumps(MyClass[int, 5]())).x == 5
    """

    def __init__(self, name, cls, argtypes, args=()):
        self.__qualname__ = name
        self.__doc__ = cls.__doc__
        self.name = name
        self.cls = cls
        self.argtype = argtypes[0](self.name, self._chain)
        self.argtypes = argtypes[1:]
        self.args = args

    def _chain(self, name, arg):
        if self.argtypes:
            return type(self)(name, self.cls, self.argtypes, (*self.args, arg))
        return self.cls(name, *self.args, arg)

    @saveattr
    def __getattr__(self, name):
        return getattr(self.argtype, name)

    def __getitem__(self, args):
        if not isinstance(args, tuple):
            args = (args,)

        argtype = self.argtype
        for arg in args:
            argtype = argtype[arg]
        return argtype

class ListType:
    """Helper to combine other types.

    This is a helper class to allow classes which are polymorphic over multiple
    types to be pickled. For example::

        import pickle
        from mpmetrics.generics import IntType, ListType

        def MyClass(__name__, xs):
            return type(__name__, (), locals())

        MyClass = ListType('MyClass', MyClass, IntType)
        assert MyClass[1, 2, 3].xs == (1, 2, 3)
        assert pickle.loads(pickle.dumps(MyClass[1, 2, 3]())).xs == (1, 2, 3)
    """

    def __init__(self, name, cls, elemtype):
        self.__qualname__ = name
        self.__doc__ = cls.__doc__
        self.name = name
        self.cls = cls
        self.elemtype = elemtype
        self.length = IntType(name, self._begin)

    def _begin(self, name, length):
        return ProductType(name, self._end, (self.elemtype,) * length)

    def _end(self, name, *elems):
        return self.cls(name, elems)

    @saveattr
    def __getattr__(self, name):
        return getattr(self.length, name)

    def __getitem__(self, args):
        if not isinstance(args, tuple):
            args = (args,)

        return getattr(self, str(len(args)))[args]
