# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2022 Sean Anderson <seanga2@gmail.com>

import math
import mmap

import pytest
from hypothesis import given, HealthCheck, settings, strategies as st

from mpmetrics.heap import Heap
from mpmetrics.util import align

from .common import parallel

@given(st.integers().filter(lambda n: n % mmap.PAGESIZE))
def test_bad_map_size(map_size):
    with pytest.raises(ValueError):
        Heap(map_size=map_size)

@given(st.integers(max_value=0))
def test_small_size(size):
    with pytest.raises(ValueError):
        Heap().malloc(size)

@given(st.integers().filter(lambda a: a <= 0 or math.log2(a) % 1))
def test_bad_align(alignment):
    with pytest.raises(ValueError):
        Heap().malloc(1, alignment)

@st.composite
def allocs(draw):
    size = mmap.ALLOCATIONGRANULARITY << draw(st.integers(0, 4))
    heap = Heap(map_size=size)
    sizes = st.integers(1, 2 * size)
    aligns = st.integers(0, 12).map(lambda n: 1 << n)
    return heap, draw(st.lists(st.tuples(sizes, aligns), min_size=3))

@given(allocs())
@settings(max_examples=25, suppress_health_check=(HealthCheck.data_too_large,))
def test_malloc(alloc):
    h, paramlist = alloc

    blocks = [h.malloc(*params) for params in paramlist]
    for ((size, alignment), block) in zip(paramlist, blocks):
        if size < h.map_size:
            assert block.size == size
        else:
            assert block.size >= size
        assert block.start == align(block.start, alignment)

    mems = [block.deref() for block in blocks]
    for (block, mem) in zip(blocks, mems):
        if size < h.map_size:
            assert len(mem) == block.size
        else:
            assert len(mem) >= block.size
        assert not any(mem)
        mem[:] = b'A' * len(mem)

    blocks.sort(key=lambda block: block.start)
    for i in range(len(blocks)):
        if i:
            prev = blocks[i - 1]
            assert prev.start + prev.size <= blocks[i].start

def setone(block):
    block.deref()[0] = 1

def test_prefork(parallel):
    block = Heap().malloc(1)
    mem = block.deref()
    assert mem[0] == 0

    p = parallel.spawn(target=setone, args=(block,))
    p.start()
    p.join()
    assert mem[0] == 1

def settwo(q):
    mem = q.get().deref()
    mem[0] = 2

def test_postfork(parallel):
    q = parallel.queue()
    p = parallel.spawn(target=settwo, args=(q,))
    p.start()

    h = Heap()
    h.malloc(mmap.PAGESIZE)
    block = h.malloc(1)
    q.put(block)
    p.join()
    assert block.deref()[0] == 2
