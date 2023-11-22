# SPDX-License-Identifier: LGPL-3.0-only
# Copyright (C) 2021-22 Sean Anderson <seanga2@gmail.com>

"""A shared memory allocator."""

import itertools
import mmap
from multiprocessing.reduction import DupFd
import os
from tempfile import TemporaryFile
import threading

import _mpmetrics
from .types import Size_t, Struct
from .util import align, _align_check

SC_LEVEL1_DCACHE_LINESIZE = 190
try:
    CACHELINESIZE = os.sysconf(SC_LEVEL1_DCACHE_LINESIZE)
except OSError:
    CACHELINESIZE = 64 # Assume 64-byte cache lines

PAGESIZE = 4096

class Heap(Struct):
    """A shared memory allocator.

    This is a basic arena-style allocator. The core algorithm is (effectively)::

        def malloc(size):
            old_base = base
            base += size
            return old_base

    We do not keep track of free blocks, so :py:meth:`Heap.Block.free` is a no-op.

    Memory is requested from the OS in page-sized blocks. As we don't map all
    of our memory up front, it's possible that different processes will map new
    pages at different addresses. Therefore, we keep track of the address where
    each page is mapped, and ensure blocks do not cross page boundaries.
    Larger-than-page-size blocks are supported by aligning the block to the
    page size and mapping all pages in that block in one go.
    """

    _fields_ = {
        '_shared_lock': _mpmetrics.Lock,
        '_base': Size_t,
    }

    def __init__(self, map_size=PAGESIZE):
        """Create a new Heap.

        :param int map_size: The granularity to use when requesting memory from the OS
        """

        if map_size % mmap.ALLOCATIONGRANULARITY:
            raise ValueError("size must be a multiple of {}".format(mmap.ALLOCATIONGRANULARITY))
        _align_check(map_size)
        self.map_size = map_size

        # File backing our shared memory
        self._file = TemporaryFile()
        self._fd = self._file.fileno()
        # Allocate a page to start with
        os.truncate(self._fd, map_size)

        # Process-local shared memory maps
        self._maps = [mmap.mmap(self._fd, map_size)]
        # Lock for _maps
        self._lock = threading.Lock()

        super().__init__(memoryview(self._maps[0])[:self.size])
        self._base.value = self.size

    def __getstate__(self):
        return self.map_size, DupFd(self._fd)

    def __setstate__(self, state):
        self.map_size, df = state
        self._fd = df.detach()
        self._file = open(self._fd, 'a+b')

        # Process-local shared memory maps
        self._maps = [mmap.mmap(self._fd, self.map_size)]
        # Lock for _maps
        self._lock = threading.Lock()

        super()._setstate(memoryview(self._maps[0])[:self.size])

    class Block:
        """A block of memory allocated from a Heap."""

        def __init__(self, heap, start, size):
            """Create a new Block.

            :param Heap heap: The heap this block is from
            :param int start: The offset of this block within the heap
            :param int size: The size of this block
            """

            self.heap = heap
            self.start = start
            self.size = size

        def deref(self):
            """Dereference this block

            :return: The memory referenced by this block
            :rtype: memoryview

            Dereference the block, faulting in unmapped pages as necessary.
            """

            heap = self.heap
            first_page = int(self.start / heap.map_size)
            last_page = int((self.start + self.size - 1) / heap.map_size)
            nr_pages = last_page - first_page + 1
            page_off = first_page * heap.map_size
            off = self.start - page_off
            with heap._lock:
                if len(heap._maps) <= last_page:
                    heap._maps.extend(itertools.repeat(None, last_page - len(heap._maps) + 1))
                if not self.heap._maps[first_page]:
                    heap._maps[first_page] = mmap.mmap(heap._fd, heap.map_size * nr_pages,
                                                       offset=page_off)
                map = heap._maps[first_page]

            return memoryview(map)[off:off+self.size]

        def free(self):
            """Free this block"""
            pass

    def malloc(self, size, alignment=CACHELINESIZE):
        """Allocate shared memory.

        :param int size: The amount of shared memory to allocate, in bytes
        :param int alignment: The minimum alignment of the memory
        :return: A block of shared memory
        :rtype: Block

        Allocate at least `size` bytes of shared memory. It will be aligned to
        at least `alignment`.
        """

        if size <= 0:
            raise ValueError("size must be strictly positive")
        elif size > self.map_size:
            size = align(size, self.map_size)
        _align_check(alignment)

        with self._shared_lock:
            total = align(self._base.value, self.map_size)
            self._base.value = align(self._base.value, alignment)
            if self._base.value + size >= total:
                os.ftruncate(self._fd, align(total + size, self.map_size))
                self._base.value = total
            start = self._base.value
            self._base.value += size

        return self.Block(self, start, size)
