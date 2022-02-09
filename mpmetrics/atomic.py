# SPDX-License-Identifier: LGPL-3.0-only
# Copyright (C) 2022 Sean Anderson <seanga2@gmail.com>

import _mpmetrics
from .types import Double, Int64, UInt64, Struct

# TODO: Rewrite this in C if anyone cares about performance on arches without 64-bit atomics?

class _Locking(Struct):
    _fields_ = {
        '_lock': _mpmetrics.Lock,
    }

    def get(self):
        with self._lock:
            return self._value.value

    def set(self, value):
        with self._lock:
            self._value.value = value

    def add(self, amount, raise_on_overflow=True):
        with self._lock:
            old = self._value.value
            self._value.value = old + amount
            if raise_on_overflow and self._value.value != old + amount:
                raise OverflowError(f"{old} + {amount} too large to fit")
            return old

class LockingDouble(_Locking):
    _fields_ = _Locking._fields_ | {
        '_value': Double,
    }

class LockingInt64(_Locking):
    _fields_ = _Locking._fields_ | {
        '_value': Int64,
    }

class LockingUInt64(_Locking):
    _fields_ = _Locking._fields_ | {
        '_value': UInt64,
    }

AtomicDouble = _mpmetrics.AtomicDouble or LockingDouble
AtomicInt64 = _mpmetrics.AtomicInt64 or LockingInt64
AtomicUInt64 = _mpmetrics.AtomicUInt64 or LockingUInt64
