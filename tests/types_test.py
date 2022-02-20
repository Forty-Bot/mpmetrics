# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2022 Sean Anderson <seanga2@gmail.com>

import pickle

from hypothesis import assume, given, reject, settings, strategies as st
from hypothesis.stateful import Bundle, RuleBasedStateMachine, rule
import pytest

from mpmetrics.atomic import AtomicInt64, AtomicUInt64, AtomicDouble
from mpmetrics.generics import ObjectType, ListType
from mpmetrics.heap import PAGESIZE, Heap
from mpmetrics.types import Array, Box, Dict, Double, Size_t, Struct
from _mpmetrics import Lock

from .common import heap

def GenericStruct(__name__, classes):
    ns = { '_fields_': { str(i): cls for i, cls in enumerate(classes)}}
    return type(__name__, (Struct,), ns)

GenericStruct = ListType('GenericStruct', GenericStruct, ObjectType) 

def recursive_types(classes):
    @st.composite
    def arrays(draw):
        array = Array[draw(classes), draw(st.integers(1, 8))]
        # reject too-large types as soon as we can
        if array.size >= PAGESIZE:
            reject()
        return array

    @st.composite
    def structs(draw):
        n = draw(st.integers(1, 8))
        struct = GenericStruct[draw(st.tuples(*((classes,) * n)))]
        # ditto
        if struct.size >= PAGESIZE:
            reject()
        return struct

    return arrays() | structs()

base_types = st.sampled_from((AtomicInt64, AtomicUInt64, AtomicDouble, Double, Size_t, Lock))
types = st.recursive(base_types, recursive_types)

@given(types)
@settings(max_examples=25)
def test_pickle(heap, cls):
    pickle.loads(pickle.dumps(cls))

    assume(cls.size <= heap.map_size)
    v = Box[cls](heap)
    pickle.loads(pickle.dumps(v))

# We use Size_t because drawing from types is slow
@given(st.integers(min_value=1))
def test_array(heap, n):
    A = Array[Size_t, n]
    assert A.size >= n * Size_t.size

    assume(A.size <= heap.map_size)
    a = Box[A](heap)
    assert len(a) == n

@given(st.integers(max_value=0))
def test_bad_size(n):
    with pytest.raises(ValueError):
        Array[Size_t, n]

@settings(max_examples=25)
class DictComparison(RuleBasedStateMachine):
    keys = Bundle('keys')
    values = Bundle('values')
    heap = Heap()

    def __init__(self):
        super().__init__()
        self.dict = Box[Dict](self.heap)
        self.model = {}

    @rule(target=keys, k=st.text())
    def key(self, k):
        return k

    @rule(target=values, v=st.text())
    def value(self, v):
        return v

    @rule()
    def len(self):
        assert len(self.model) == len(self.dict)

    @rule(k=keys)
    def getitem(self, k):
        try:
            model_k = self.model[k]
        except KeyError:
            with pytest.raises(KeyError):
                dict_k = self.dict[k]
        else:
            dict_k = self.dict[k]
            assert model_k == dict_k

    @rule(k=keys, v=values)
    def setitem(self, k, v):
        self.model[k] = v
        self.dict[k] = v

    @rule(k=keys)
    def delitem(self, k):
        try:
            del self.model[k]
        except KeyError:
            with pytest.raises(KeyError):
                del self.dict[k]
        else:
            del self.dict[k]

    @rule()
    def iters(self):
        for f in (
            iter,
            reversed,
            lambda d: d.items(),
            lambda d: d.keys(),
            lambda d: d.values(),
        ):
            for m, d in zip(f(self.model), f(self.dict)):
                assert m == d

    @rule(k=keys)
    def contains(self, k):
        assert (k in self.model) == (k in self.dict)

    @rule(other=st.dictionaries(keys, values))
    def update(self, other):
        self.model.update(other)
        self.dict.update(other)

    @rule(other=st.dictionaries(keys, values))
    def ior(self, other):
        self.model |= other
        self.dict |= other

    @rule(other=st.dictionaries(keys, values))
    def union(self, other):
        assert (self.model | other) == (self.dict | other)

    @rule()
    def clear(self):
        self.model.clear()
        self.dict.clear()

DictTest = DictComparison.TestCase
