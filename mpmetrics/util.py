# SPDX-License-Identifier: LGPL-3.0-only
# Copyright (C) 2022 Sean Anderson <seanga2@gmail.com>

def _align_mask(x, mask):
    return (x + mask) & ~mask

def _align_check(a):
    if not a or a & (a - 1):
        raise ValueError("{} is not a power of 2".format(a))

def align(x, a):
    _align_check(a)
    return _align_mask(x, a - 1)

def align_down(x, a):
    _align_check(a)
    return x & ~(a - 1)

def genmask(hi, lo):
    return (-1 << lo) & ~(-1 << (hi + 1))

# From https://stackoverflow.com/a/7864317/5086505
class classproperty(property):
    def __get__(self, cls, owner):
        return classmethod(self.fget).__get__(None, owner)()
