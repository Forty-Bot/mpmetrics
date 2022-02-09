# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2022 Sean Anderson <seanga2@gmail.com>

from copy import copy
import time

import pytest

from mpmetrics.types import Box
from _mpmetrics import Lock

from .common import heap, parallel

def test_basics(heap):
    l1 = Box[Lock](heap)

    assert l1.acquire()
    with pytest.raises(OSError):
        l1.acquire()

    l2 = copy(l1)
    with pytest.raises(OSError):
        l2.acquire()

    l1.release()
    with pytest.raises(PermissionError):
        l1.release()

    with l1:
        with pytest.raises(OSError):
            l2.acquire()

    assert l1.acquire(block=False)
    l1.release()

    assert l1.acquire(timeout=1)
    l1.release()

def test_acquire(heap, parallel):
    def hold(l, b):
        with l:
            b.wait()
            b.wait()

    l = Box[Lock](heap)
    b = parallel.barrier(2)
    p = parallel.spawn(target=hold, args=(l, b))
    p.start()

    try:
        b.wait()
        assert not l.acquire(block=False)
        now = time.time()
        assert not l.acquire(timeout=0.001)
        assert now + 0.001 <= time.time()
        b.wait()
        with l:
            pass
    except:
        b.abort()
        raise
    finally:
        p.join()
