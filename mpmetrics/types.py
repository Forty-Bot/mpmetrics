# SPDX-License-Identifier: LGPL-3.0-only
# Copyright (C) 2022 Sean Anderson <seanga2@gmail.com>

import ctypes

from .generics import IntType, ObjectType, ProductType
from .util import align, classproperty

def _wrap_ctype(__name__, ctype):
    size = ctypes.sizeof(ctype)
    align = ctypes.alignment(ctype)

    def __init__(self, mem, init=True):
        self._mem = mem
        self._value = ctype.from_buffer(mem)

    def __getattr__(self, name):
        return getattr(self.__dict__['_value'], name)

    def __setattr__(self, name, value):
        if '_value' in self.__dict__:
            setattr(self.__dict__['_value'], name, value)
        else:
            self.__dict__[name] = value

    def __delattr__(self, name):
        delattr(self.__dict__['_value'], name)

    return type(__name__, (), { name: value for name, value in locals().items()
                                if name != 'ctype'})

Double = _wrap_ctype('Double', ctypes.c_double)
Size_t = _wrap_ctype('Size_t', ctypes.c_size_t)
Int64 = _wrap_ctype('Int64', ctypes.c_int64)
UInt64 = _wrap_ctype('UInt64', ctypes.c_uint64)

class Struct:
    def __init__(self, mem, init=True):
        self._mem = mem
        off = 0
        for name, field in self._fields_.items():
            off = align(off, field.align)
            setattr(self, name, field(mem[off:off + field.size], init))
            off += field.size
            
    @classproperty
    def size(cls):
        size = 0
        for name, field in cls._fields_.items():
            size = align(size, field.align)
            size += field.size
        return size

    @classproperty
    def align(cls):
        return max(field.align for name, field in cls._fields_.items())

def Array(__name__, cls, n):
    if n < 1:
        raise ValueError("n must be strictly positive")

    member_size = align(cls.size, cls.align)
    size = member_size * n

    def __init__(self, mem, init=True):
        self._mem = mem
        self._vals = []
        for i in range(n):
            off = i * member_size
            self._vals.append(cls(mem[off:off + member_size], init))

    def __len__(self):
        return n

    def __getitem__(self, key):
        return self._vals[key]

    def __setitem__(self, key, value):
        self._vals[key] = value

    def __iter__(self):
        return iter(self._vals)

    ns = locals()
    ns['align'] = cls.align
    del ns['member_size']
    del ns['cls']
    del ns['n']

    return type(__name__, (), ns)

Array = ProductType('Array', Array, (ObjectType, IntType))

class _Box:
    def __init__(self, heap, *args, **kwargs):
        self._args = args
        self._kwargs = kwargs
        block = heap.malloc(self.size)
        super().__init__(block.deref(), init=True, *self._args, **self._kwargs)
        self._block = block

    def __getstate__(self):
        return self._block, self._args, self._kwargs

    def __setstate__(self, state):
        self._block, self._args, self._kwargs = state
        super().__init__(self._block.deref(), init=False, *self._args, **self._kwargs)

Box = ObjectType('Box', lambda name, cls: type(name, (_Box, cls), {}))
