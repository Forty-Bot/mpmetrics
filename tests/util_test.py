# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2022 Sean Anderson <seanga2@gmail.com>

import math
import mmap

import pytest
from hypothesis import assume, given, strategies as st

from mpmetrics.util import align, align_down, genmask

@given(st.integers(), st.integers(0, 100).map(lambda n: 1 << n))
def test_align(x, a):
    res = align(x, a)
    assert res % a == 0
    assert res >= x
    assert res - a < x

    res = align_down(x, a)
    assert res % a == 0
    assert res <= x
    assert res + a >= x

@given(st.integers(), st.integers(1).filter(lambda a: math.log2(a) % 1))
def test_npot(x, a):
    with pytest.raises(ValueError):
        align(x, a)

    with pytest.raises(ValueError):
        align_down(x, a)

@given(st.integers(0, 63), st.integers(0, 63))
def test_genmask(hi, lo):
    assume(hi >= lo)
    for bit in range(lo, hi):
        assert (1 << bit) & genmask(hi, lo)
