# SPDX-License-Identifier: LGPL-3.0-only
# Copyright (C) 2022 Sean Anderson <seanga2@gmail.com>

"""Various small utilities."""

def _align_mask(x, mask):
    return (x + mask) & ~mask

def _align_check(a):
    if not a or a & (a - 1):
        raise ValueError("{} is not a power of 2".format(a))

def align(x, a):
    """Align `x` to `a`

    :param int x: The value to align
    :param int a: The alignment; must be a power of two
    :return: The smallest multiple of `a` greater than `x`
    :rtype: int
    """

    _align_check(a)
    return _align_mask(x, a - 1)

def align_down(x, a):
    """Align `x` down to `a`

    :param int x: The value to align
    :param int a: The alignment; must be a power of two
    :return: The largest multiple of `a` less than `x`
    :rtype: int
    """

    _align_check(a)
    return x & ~(a - 1)

def genmask(hi, lo):
    """Generate a mask with bits between `hi` `lo` set.

    :param int hi: The highest bit to set, inclusive
    :param int lo: The lowest bit to set, inclusive
    :return: The bitmask
    :rtype: int

    `hi` must be greater than `lo`. Bits are numbered in "little-endian" order,
    starting from zero. The following invariant holds::

        mask = 0
        for n in range(lo, hi):
            mask |= 1 << n
        assert mask == genmask(hi, lo)
    """

    return (-1 << lo) & ~(-1 << (hi + 1))

# From https://stackoverflow.com/a/7864317/5086505
class classproperty(property):
    """Like `property` but for classes."""
    def __get__(self, cls, owner):
        return classmethod(self.fget).__get__(None, owner)()
