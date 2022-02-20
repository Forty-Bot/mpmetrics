# SPDX-License-Identifier: LGPL-3.0-only
# Copyright (C) 2022 Sean Anderson <seanga2@gmail.com>

import ctypes
import pickle

from .generics import IntType, ObjectType, ProductType
from .util import align, classproperty

def _wrap_ctype(__name__, ctype):
    size = ctypes.sizeof(ctype)
    align = ctypes.alignment(ctype)

    def __init__(self, mem, heap=None):
        self._mem = mem
        self._value = ctype.from_buffer(mem)
        self._value.value = 0

    def _setstate(self, mem, heap=None):
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
    @classmethod
    def _fields_iter(cls):
        off = 0
        for name, field in cls._fields_.items():
            off = align(off, field.align)
            yield name, field, off
            off += field.size

    @classproperty
    def size(cls):
        for name, field, off in cls._fields_iter():
            size = field.size + off
        return size

    @classproperty
    def align(cls):
        return max(field.align for field in cls._fields_.values())

    def __init__(self, mem, heap=None):
        self._mem = mem
        for name, field, off in self._fields_iter():
            setattr(self, name, field(mem[off:off + field.size], heap=heap))

    def _setstate(self, mem, heap=None):
        self._mem = mem
        for name, field, off in self._fields_iter():
            field = field.__new__(field)
            field._setstate(self._mem[off:off + field.size], heap=heap)
            setattr(self, name, field)

def Array(__name__, cls, n):
    if n < 1:
        raise ValueError("n must be strictly positive")

    member_size = align(cls.size, cls.align)
    size = member_size * n

    def __init__(self, mem, heap=None):
        self._mem = mem
        self._vals = []
        for i in range(n):
            off = i * member_size
            self._vals.append(cls(self._mem[off:off + member_size], heap=heap))

    def _setstate(self, mem, heap=None):
        self._mem = mem
        self._vals = []
        for i in range(n):
            off = i * member_size
            val = cls.__new__(cls)
            val._setstate(self._mem[off:off + member_size], heap=heap)
            self._vals.append(val)

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
        block = heap.malloc(self.size)
        super().__init__(block.deref(), *args, heap=heap, **kwargs)
        self.__block = block

    def __getstate__(self):
        return self.__block

    def __setstate__(self, state):
        self.__block = state
        super()._setstate(self.__block.deref(), heap=self.__block.heap)

Box = ObjectType('Box', lambda name, cls: type(name, (_Box, cls), {}))

class Dict(Struct):
    _fields_ = {
        '_start': Size_t,
        '_size': Size_t,
        '_len': Size_t,
    }

    def __init__(self, mem, heap):
        if not heap:
            raise ValueError("heap must be provided")
        super().__init__(mem)
        self._heap = heap

    def _setstate(self, mem, heap):
        super()._setstate(mem, heap)
        self._heap = heap

    @property
    def _block(self):
        if self._size.value:
            return self._heap.Block(self._heap, self._start.value, self._size.value)

    @_block.setter
    def _block(self, block):
        self._start.value = block.start
        self._size.value = block.size

    @property
    def _dict(self):
        if self._len.value:
            return pickle.loads(self._block.deref()[:self._len.value])
        return {}

    @_dict.setter
    def _dict(self, d):
        ds = pickle.dumps(d)
        new_length = len(ds)
        self._len.value = new_length
        if self._len.value > self._size.value:
            if self._size.value:
                self._block.free()
            # Scale by a lot to minimize allocations; Heap doesn't free backing memory
            self._block = self._heap.malloc(4 * new_length)
        self._block.deref()[:self._len.value] = ds

    def __repr__(self):
        return f"{self.__class__.__qualname__}({repr(self._dict)})"

    def __len__(self):
        return len(self._dict)

    def __getitem__(self, key):
        return self._dict[key]

    def __setitem__(self, key, value):
        d = self._dict
        d[key] = value
        self._dict = d

    def __delitem__(self, key):
        d = self._dict
        del d[key]
        self._dict = d

    def __iter__(self):
        return iter(self._dict)

    def __reversed__(self):
        return reversed(self._dict)

    def __contains__(self, item):
        return item in self._dict

    def __or__(self, other):
        return self._dict | other

    def __ior__(self, other):
        self._dict = self._dict | other
        return self

    def clear(self):
        self._len.value = 0

    def copy(self):
        return self._dict

    def get(self, key, default=None):
        return self._dict.get(key, default)

    def items(self):
        return self._dict.items()

    def keys(self):
        return self._dict.keys()

    def values(self):
        return self._dict.values()

    def update(self, other=()):
        d = self._dict
        d.update(other)
        self._dict = d
