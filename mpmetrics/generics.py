# SPDX-License-Identifier: LGPL-3.0-only
# Copyright (C) 2022 Sean Anderson <seanga2@gmail.com>

import importlib
import itertools

def saveattr(get):
    def wrapped(self, name):
        attr = get(self, name)
        setattr(self, name, attr)
        return attr
    return wrapped

class ObjectType:
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
        setattr(self, '<', self.Module(name + '.<', cls))

    def __getitem__(self, cls):
        parent = getattr(self, '<')
        for subpath in itertools.chain(cls.__module__.split('.'), cls.__qualname__.split('.')):
            parent = getattr(parent, subpath)
        return getattr(parent, '>')

class IntType:
    def __init__(self, name, cls):
        self.__qualname__ = name
        self.name = name
        self.cls = cls

    @saveattr
    def __getattr__(self, attr):
        return self.cls(self.name + '.' + attr, int(attr))

    def __getitem__(self, n):
        return getattr(self, repr(n))

class FloatType:
    def __init__(self, name, cls):
        self.__qualname__ = name
        self.name = name
        self.cls = cls

    @saveattr
    def __getattr__(self, attr):
        return self.cls(self.name + '.' + attr, float(attr.replace('_', '.')))

    def __getitem__(self, n):
        return getattr(self, repr(n).replace('.', '_'))


class ProductType:
    def __init__(self, name, cls, argtypes, args=()):
        self.__qualname__ = name
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
    def __init__(self, name, cls, elemtype):
        self.__qualname__ = name
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
