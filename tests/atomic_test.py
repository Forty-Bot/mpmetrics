# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2022 Sean Anderson <seanga2@gmail.com>

from contextlib import nullcontext
import math

from hypothesis import given, strategies as st
import pytest

from mpmetrics.types import Box, Double
from mpmetrics.atomic import AtomicInt64, AtomicUInt64, AtomicDouble

from .common import heap, parallel, parallels, ParallelLoop

@pytest.fixture(scope='module', params=(AtomicInt64, AtomicUInt64, AtomicDouble))
def atomic(request):
    return Box[request.param]

@pytest.fixture(scope='module', params=(AtomicInt64, AtomicUInt64))
def integer(request):
    return Box[request.param]

@given(st.integers())
def test_iset(heap, integer, x):
    a = integer(heap)
    if x not in range(a.min, a.max):
        ctx = pytest.raises(OverflowError)
    else:
        ctx = nullcontext()
    with ctx:
        a.set(x)

def integers():
    return st.integers(AtomicInt64.min, AtomicInt64.max)

@given(integers(), integers())
def test_iadd(heap, x, y):
    a = Box[AtomicInt64](heap)
    a.set(x)
    if x + y not in range(a.min, a.max):
        with pytest.raises(OverflowError):
            a.add(y)
    else:
        a.add(y)
        assert a.get() == x + y

def unsigned_integers():
    return st.integers(AtomicUInt64.min, AtomicUInt64.max)

@given(unsigned_integers(), unsigned_integers())
def test_uadd(heap, x, y):
    a = Box[AtomicUInt64](heap)
    a.set(x)
    if x + y not in range(a.min, a.max):
        with pytest.raises(OverflowError):
            a.add(y)
    else:
        a.add(y)
        assert a.get() == x + y

@given(x=st.floats())
def test_dset(heap, x):
    a = Box[AtomicDouble](heap)
    a.set(x)

@given(x=st.floats(), y=st.floats())
def test_dadd(heap, x, y):
    a = Box[AtomicDouble](heap)
    a.set(x)
    a.add(y)
    if math.isnan(x + y):
        assert math.isnan(a.get())
    else:
        assert a.get() == x + y

def test_ordering(heap, atomic, parallel):
    class Test(ParallelLoop):
        def __init__(self):
            super().__init__(parallel)
            self.x = atomic(heap)
            self.y = atomic(heap)

        def loop(self, n):
            self.x.add(1)
            self.y.add(1)

        def check(self):
            y = self.y.get()
            x = self.x.get()
            assert x >= y

        def final(self):
            assert self.x.get() == self.total
            assert self.y.get() == self.total

    Test().run()

def test_racy(heap):
    class Test(ParallelLoop):
        def __init__(self):
            super().__init__(parallels['process'])
            self.value = Box[Double](heap)

        def loop(self, n):
            self.value.value += 1

        def final(self):
            assert self.value.value != self.total

    Test().run()
