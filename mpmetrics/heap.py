# SPDX-License-Identifier: LGPL-3.0-only
# Copyright (C) 2021-22 Sean Anderson <seanga2@gmail.com>

import itertools
import mmap
import os
from tempfile import NamedTemporaryFile
import threading
from weakref import WeakValueDictionary

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
    _fields_ = {
        '_shared_lock': _mpmetrics.Lock,
        '_base': Size_t,
    }

    # Only create one heap per process to avoid duplicate mappings
    _heaps_lock = threading.Lock()
    _heaps = WeakValueDictionary()

    def __new__(cls, map_size=PAGESIZE, filename=None):
        cls._heaps_lock.acquire()
        try:
            if filename:
                if heap := cls._heaps.get(filename, None):
                    return heap

            return super().__new__(cls)
        except:
            cls._heaps_lock.release()
            raise

    # Must be called with Heap._heaps_lock held; it will be released
    def __init__(self, map_size=PAGESIZE, filename=None):
        try:
            if filename:
                return

            if map_size % mmap.ALLOCATIONGRANULARITY:
                raise ValueError("size must be a multiple of {}".format(mmap.ALLOCATIONGRANULARITY))
            _align_check(map_size)
            self.map_size = map_size

            # File backing our shared memory
            self._file = NamedTemporaryFile()
            self._fd = self._file.fileno()
            # Allocate a page to start with
            os.truncate(self._fd, map_size)

            # Process-local shared memory maps
            self._maps = [mmap.mmap(self._fd, map_size)]
            # Lock for _maps
            self._lock = threading.Lock()

            super().__init__(memoryview(self._maps[0])[:self.size])
            self._base.value = self.size

            # Add ourself to the list of heaps
            self._heaps[self._file.name] = self
        finally:
            self._heaps_lock.release()

    def __getnewargs__(self):
        return self.map_size, self._file.name

    def __getstate__(self):
        return self.map_size, self._file.name

    def __setstate__(self, state):
        try:
            if hasattr(self, '_file'):
                return

            self.map_size, filename = state
            self._file = open(filename, 'a+b')
            self._fd = self._file.fileno()

            # Process-local shared memory maps
            self._maps = [mmap.mmap(self._fd, self.map_size)]
            # Lock for _maps
            self._lock = threading.Lock()

            super()._setstate(memoryview(self._maps[0])[:self.size])

            # Add ourself to the list of heaps
            self._heaps[self._file.name] = self
        finally:
            self._heaps_lock.release()

    def __del__(self):
        if hasattr(self, '_file'):
            self._file.close()

    class Block:
        def __init__(self, heap, start, size):
            self.heap = heap
            self.start = start
            self.size = size

        def deref(self):
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
            pass

    def malloc(self, size, alignment=CACHELINESIZE):
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
