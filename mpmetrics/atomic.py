# SPDX-License-Identifier: LGPL-3.0-only
# Copyright (C) 2022 Sean Anderson <seanga2@gmail.com>

"""
multiprocess-safe atomics

This module contains atomic types which automatically fall back to locking
implementations on architectures which only support 32-bit atomics.

.. py:data:: AtomicDouble

    Either :py:class:`_mpmetrics.AtomicDouble`, or :py:class:`LockingDouble` if
    the former is not supported.

.. py:data:: AtomicInt64

    Either :py:class:`_mpmetrics.AtomicInt64`, or :py:class:`LockingInt64` if
    the former is not supported.

.. py:data:: AtomicUInt64

    Either :py:class:`_mpmetrics.AtomicUInt64`, or :py:class:`LockingUInt64` if
    the former is not supported.
"""

import _mpmetrics
from .types import Double, Int64, UInt64, Struct

# TODO: Rewrite this in C if anyone cares about performance on arches without 64-bit atomics?

class _Locking(Struct):
    _fields_ = {
        '_lock': _mpmetrics.Lock,
    }

    def get(self):
        """Return the current value of the backing atomic"""
        with self._lock:
            return self._value.value

    def set(self, value):
        """Set the backing atomic to `value`."""
        with self._lock:
            self._value.value = value

    def add(self, amount, raise_on_overflow=True):
        """Add 'amount' to the backing atomic.

        :param Union[int, float] amount: The amount to add
        :param bool raise_on_overflow: Whether to raise an exception on overflow
        :return: The value from before the addition.
        :rtype: Union[int, float]
        """

        with self._lock:
            old = self._value.value
            self._value.value = old + amount
            if raise_on_overflow and self._value.value != old + amount:
                raise OverflowError(f"{old} + {amount} too large to fit")
            return old

class LockingDouble(_Locking):
    """An atomic double implemented using a lock"""

    _fields_ = _Locking._fields_ | {
        '_value': Double,
    }

class LockingInt64(_Locking):
    """An atomic 64-bit signed integer implemented using a lock"""

    _fields_ = _Locking._fields_ | {
        '_value': Int64,
    }

class LockingUInt64(_Locking):
    """An atomic 64-bit unsigned integer implemented using a lock"""

    _fields_ = _Locking._fields_ | {
        '_value': UInt64,
    }

AtomicDouble = _mpmetrics.AtomicDouble or LockingDouble
AtomicInt64 = _mpmetrics.AtomicInt64 or LockingInt64
AtomicUInt64 = _mpmetrics.AtomicUInt64 or LockingUInt64
