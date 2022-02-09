# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2022 Sean Anderson <seanga2@gmail.com>

import pickle

from hypothesis import assume, given, reject, settings, strategies as st
import pytest

from mpmetrics.atomic import AtomicInt64, AtomicUInt64, AtomicDouble
from mpmetrics.generics import ObjectType, ListType
from mpmetrics.heap import PAGESIZE
from mpmetrics.types import Array, Box, Double, Size_t, Struct
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
types = st.recursive(base_types, recursive_types, max_leaves=20)

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
