# SPDX-License-Identifier: LGPL-3.0-only
# Copyright (C) 2022 Sean Anderson <seanga2@gmail.com>

"""Various types backed by (shared) memory"""

import ctypes
import io
from multiprocessing.reduction import ForkingPickler
import pickle
import sys

from .generics import IntType, ObjectType, ProductType
from .util import align, classproperty

def _wrap_ctype(__name__, ctype, doc):
    size = ctypes.sizeof(ctype)
    align = ctypes.alignment(ctype)

    __doc__ = f"""{doc.capitalize()} backed by (shared) memory.

    .. py:attribute:: value
        :type: {'float' if __name__ == 'Double' else 'int'}

        The value itself. You can read and modify this value as necessary. For
        example::

            from mpmetrics.heap import Heap
            from mpmetrics.types import Box, {__name__}

            var = Box[{__name__}](Heap())
            assert var.value == 0
            var.value += 1
            assert var.value == 1

    .. py:attribute:: size
        :type: int
        :value: {size}

        The size of {doc}, in bytes

    .. py:attribute:: align
        :type: int
        :value: {align}

        The alignment of {doc}, in bytes
    """

    def __init__(self, mem, heap=None):
        self._mem = mem
        self._value = ctype.from_buffer(mem)
        self._value.value = 0

    __init__.__doc__ = f"""Create a new {__name__}.

    :param memoryview mem: The backing memory
    :param heap: Unused
    """

    def _setstate(self, mem, heap=None, **kwargs):
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

    ns = locals()
    del ns['doc']
    del ns['ctype']
    return type(__name__, (), ns)

Double = _wrap_ctype('Double', ctypes.c_double, "a double")
Size_t = _wrap_ctype('Size_t', ctypes.c_size_t, "a size_t")
Int64 = _wrap_ctype('Int64', ctypes.c_int64, "an int64_t")
UInt64 = _wrap_ctype('UInt64', ctypes.c_uint64, "a uint64_t")

class Struct:
    """A structured group of fields backed by (shared) memory.

    This is a base class that can be subclassed to create C-style structs::

        from mpmetrics.heap import Heap
        from mpmetrics.types import Double, Size_t, Struct

        class MyStruct(mpmetrics.types.Struct):
            _fields_ = {
                'a': Double,
                'b': Size_t,
            }

        assert MyStruct.size == Double.size + Size_t.size
        s = Box[MyStruct](Heap())
        assert type(s.a) == Double
        assert type(s.b) == Size_t

    .. py:property:: _fields_
        :classmethod:
        :type: dict[str, Any]

        The fields of the struct, in order. Upon initialization, each value is
        initialized with a block of memory equal to its `.size`. Padding is
        added as necessary to ensure alignment.

        Subclasses must implement this property.
    """

    @classmethod
    def _fields_iter(cls):
        off = 0
        for name, field in cls._fields_.items():
            off = align(off, field.align)
            yield name, field, off
            off += field.size

    @classproperty
    def size(cls):
        """The size of the struct, in bytes"""
        for name, field, off in cls._fields_iter():
            size = field.size + off
        return size

    @classproperty
    def align(cls):
        """The alignment of the struct, in bytes"""
        return max(field.align for field in cls._fields_.values())

    def __init__(self, mem, heap=None):
        """Create a new Struct.

        :param memoryview mem: The backing memory
        :param mpmetrics.heap.Heap heap: Passed to each field's ``__init__``
        """

        self._mem = mem
        for name, field, off in self._fields_iter():
            setattr(self, name, field(mem[off:off + field.size], heap=heap))

    def _setstate(self, mem, heap=None, **kwargs):
        self._mem = mem
        for name, field, off in self._fields_iter():
            field = field.__new__(field)
            field._setstate(self._mem[off:off + field.size], heap=heap)
            setattr(self, name, field)

def Array(__name__, cls, n):
    """An array of values backed by (shared) memory.

    You can access values in an `Array` just like it was a `list`::

        from mpmetrics.heap import Heap
        from mpmetrics.types import Array, Box, Double

        assert Array[Double, 5].size == Double.size * 5
        a = Box[Array[Double, 5]](Heap())
        assert type(a[0]) == Double
        a[4].value = 6.28


    .. py:method:: Array.__init__(mem, heap=None)

        Create a new Array.

        :param memoryview mem: The backing memory
        :param mpmetrics.heap.Heap heap: Passed to each member's ``__init__``
    """

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

    def _setstate(self, mem, heap=None, **kwargs):
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
    """A heap-allocated box to put values in

    This class "boxes" another class using heap-allocated memory. For example,
    you could create a `Double` like::

        from mpmetrics.heap import Heap
        from mpmetrics.types import Double

        block = Heap().malloc(Double.size)
        d = Double(block.deref())

    But d._mem is a `memoryview` which can't be pickled. `Box` takes care of
    keeping track of the memory block::

        from mpmetrics.heap import Heap
        from mpmetrics.types import Box, Double

        d = Box[Double](Heap())

    .. py:method:: Box.__init__(heap, *args, **kwargs)

        Create a new object on the heap

        :param mpmetrics.heap.Heap heap: The heap to use when allocating the object
        :param \\*args: Any additional arguments are passed to the boxed class
        :param \\**kwargs: Any additional keyword arguments are passed to the boxed class.

        The superclass's `__init__` is called with a newly-allocated buffer as
        the first argument, any positional arguments to this function, the
        keyword argument `heap` set to `heap`, and any additional keyword
        arguments to this function.

    .. py:method:: Box._getstate()
        :abstractmethod:

        Return keyword arguments to pass to `_setstate`.

        :return: A dictionary of keyword arguments for `_setstate`
        :rtype: dict

        This method is optional; if it is not implemented then no additional
        keyword arguments will be passed to `_setstate`.

    .. py:method:: Box._setstate(mem, heap=None, **kwargs)
        :abstractmethod:

        Initialize internal state after unpickling.

        :param memoryview mem: The backing memory
        :param mpmetrics.heap.Heap heap: The heap `mem` was allocated from
        :param \**kwargs: Any additional arguments from `_getstate`

        This method must be implemented by boxed types.
    """

    def __init__(self, heap, *args, **kwargs):
        block = heap.malloc(self.size)
        super().__init__(block.deref(), *args, heap=heap, **kwargs)
        self.__block = block

    def __getstate__(self):
        try:
            kwargs = super()._getstate()
        except AttributeError:
            kwargs = {}
        return self.__block, kwargs

    def __setstate__(self, state):
        self.__block, kwargs = state
        super()._setstate(self.__block.deref(), heap=self.__block.heap, **kwargs)

def _create_box(name, cls):
    return type(name, (_Box, cls), {'__doc__': cls.__doc__})

_create_box.__doc__ = _Box.__doc__
Box = ObjectType('Box', _create_box)

class _Pickler(ForkingPickler):
    def __init__(self, file, heap, protocol=None):
        super().__init__(file, protocol)
        self.heap = heap

    def persistent_id(self, obj):
        if obj is self.heap:
            return 'heap'

    @classmethod
    def dumps(cls, obj, heap, protocol=None):
        buf = io.BytesIO()
        cls(buf, heap, protocol).dump(obj)
        return buf.getbuffer()

class _Unpickler(pickle.Unpickler):
    def __init__(self, file, heap):
        super().__init__(file)
        self.heap = heap

    def persistent_load(self, pid):
        if pid != 'heap':
            raise pickle.UnpicklingError(f"unsupported persistent object {pid}")
        return self.heap

    @classmethod
    def loads(cls, data, heap):
        buf = io.BytesIO(data)
        return cls(buf, heap).load()

class Object(Struct):
    """A python object pickled in (shared) memory

    This is a base class for python objects backed by shared memory. Whenever
    the object is accessed, it is unpickled from the backing memory. When it is
    modified, it is pickled to the backing memory.

    This class itself does not contain the actual object. Instead, it contains
    the start/size/length of the block containing the object. When the object
    grows too large for the block, the old block is free'd and a new one is
    allocated.

    This class provides no synchronization. All methods should be accessed
    under some other form of synchonization, such as a
    :py:class:`_mpmetrics.Lock`.
    """

    _fields_ = {
        '_start': Size_t,
        '_size': Size_t,
        '_len': Size_t,
    }

    def __init__(self, mem, heap):
        """Create a new Object.

        :param memoryview mem: The memory used to store information about the buffer
        :param mpmetrics.heap.Heap heap: The heap to use when (re)allocating the buffer
        """

        if not heap:
            raise ValueError("heap must be provided")
        super().__init__(mem)
        self._heap = heap

    def _setstate(self, mem, heap):
        assert heap is not None
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
    def _object(self):
        if self._len.value:
            return _Unpickler.loads(self._block.deref()[:self._len.value], self._heap)
        return self._new()

    @_object.setter
    def _object(self, v):
        vs = _Pickler.dumps(v, self._heap)
        new_length = len(vs)
        self._len.value = new_length
        if self._len.value > self._size.value:
            if self._size.value:
                self._block.free()
            # Scale by a lot to minimize allocations; Heap doesn't free backing memory
            self._block = self._heap.malloc(4 * new_length)
        self._block.deref()[:self._len.value] = vs

    def _mutate(self, method, *args, **kwargs):
        v = self._object
        result = getattr(v, method)(*args, **kwargs)
        self._object = v
        return result

    def __repr__(self):
        return f"{self.__class__.__qualname__}({repr(self._object)})"

class Sized:
    def __len__(self):
        return len(self._object)

class Iterable:
    def __iter__(self):
        return iter(self._object)

class Container:
    def __contains__(self, item):
        return item in self._object

class Collection(Sized, Iterable, Container):
    pass

class Reversible:
    def __reversed__(self):
        return reversed(self._object)

class Sequence(Reversible, Collection):
    def __len__(self):
        return len(self._object)

    def __getitem__(self, key):
        return self._object[key]

    def index(self, value, start=0, stop=sys.maxsize):
        return self._object.index(value, start, stop)

    def count(self, value):
        return self._object.count(value)

class MutableSequence(Sequence):
    def __setitem__(self, key, value):
        v = self._object
        v[key] = value
        self._object = v

    def __delitem__(self, key):
        v = self._object
        del v[key]
        self._object = v

    def __iadd__(self, other):
        self._object = self._object + other
        return self._object

    def insert(self, index, object):
        self._mutate('insert', index, object)

    def append(self, object):
        self._mutate('append', object)

    def reverse(self):
        self._mutate('reverse')

    def extend(self, iterable):
        self._mutate('extend', iterable)

    def pop(self, index=-1):
        return self._mutate('pop', index)

    def remove(self, value):
        self._mutate('remove', value)

class Mapping(Collection):
    def __getitem__(self, key):
        return self._object[key]

    def __eq__(self, other):
        return self._object == other

    def __neq__(self, other):
        return self._object != other

    def get(self, key, default=None):
        return self._object.get(key, default)

    def items(self):
        return self._object.items()

    def keys(self):
        return self._object.keys()

    def values(self):
        return self._object.values()

class MutableMapping(Mapping):
    def __setitem__(self, key, value):
        v = self._object
        v[key] = value
        self._object = v

    def __delitem__(self, key):
        v = self._object
        del v[key]
        self._object = v

    def clear(self):
        self._len.value = 0

    def pop(self, key, default=None):
        return self._mutate('pop', key, default)

    def popitem(self):
        return self._mutate('popitem')

    def setdefault(self, key, default=None):
        return self._mutate('setdefault', key, default)

    def update(self, other=()):
        return self._mutate('update', other)

class Dict(Object, Sequence, MutableMapping):
    """A `dict` backed by (shared) memory.

    All methods of `dict` are supported. External synchronization (such as from
    a :py:class:`_mpmetrics.Lock`) must be provided when accessing any method.
    """

    _new = dict

    def __or__(self, other):
        return self._object | other

    def __ior__(self, other):
        self._object = self._object | other
        return self

    def copy(self):
        return self._object

class List(Object, MutableSequence):
    """A `list` backed by (shared) memory.

    All methods of `list` are supported. External synchronization (such as from
    a :py:class:`_mpmetrics.Lock`) must be provided when accessing any method.
    """

    _new = list

    def sort(self, key=None, reverse=False):
        self._mutate('sort', key, reverse)
