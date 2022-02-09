# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2022 Sean Anderson <seanga2@gmail.com>

from collections import namedtuple
import multiprocessing
import queue
import threading
import time

import pytest

from mpmetrics.heap import Heap

Parallel = namedtuple('Parallel', ('spawn', 'barrier', 'queue'))
parallels = {
    'process': Parallel(
            spawn = multiprocessing.Process,
            barrier = multiprocessing.Barrier,
            queue = multiprocessing.Queue
        ),
    'thread': Parallel(
            spawn = threading.Thread,
            barrier = threading.Barrier,
            queue = queue.Queue,
        ),
}

@pytest.fixture(scope='session', params=('thread', 'process'))
def parallel(request):
    return parallels[request.param]

class ParallelLoop:
    def __init__(self, parallel, n=4, count=None):
        self.parallel = parallel
        if parallel.spawn is threading.Thread:
            n = n or 2
            count = count or 10000
        else:
            n = n or 4
            count = count or 100000
        self.n = n
        self.count = count
        self.total = n * count
        self.barrier = self.parallel.barrier(self.n + 1)

    def target(self, n):
        if hasattr(self, 'setup'):
            try:
                self.setup(n)
            except:
                self.barrier.abort()
                raise

        self.barrier.wait()
        for i in range(self.count):
            self.loop(i)

    def run(self):
        procs = [self.parallel.spawn(target=self.target, args=(i,)) for i in range(self.n)]
        for p in procs:
            p.start()
        self.barrier.wait()

        try:
            if hasattr(self, 'check'):
                while any(p.is_alive() for p in procs):
                    self.check()
                    time.sleep(0)
        except:
            for p in procs:
                if hasattr(p, 'terminate'):
                    p.terminate()
            raise
        finally:
            for p in procs:
                p.join()

        if hasattr(self, 'final'):
            self.final()

@pytest.fixture(scope="session")
def heap():
    return Heap()
