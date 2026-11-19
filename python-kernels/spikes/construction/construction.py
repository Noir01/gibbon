"""Single-schema packed-tree spike. Output bytes are caller-independent."""
import ctypes
from dataclasses import dataclass
from pathlib import Path
from build_construction import build
from readme_tree import Leaf, Node

class ConstructionOps:
    def __init__(self):
        self._lib, self.builder_body = build()
    @staticmethod
    def size(depth):
        # S(0)=9 bytes; S(d)=9+2*S(d-1), for this exact packed schema.
        return 18 * (1 << depth) - 9
    def build_tree(self, depth):
        if type(depth) is not int:
            raise TypeError('depth must be exact int')
        if not 0 <= depth <= 12:
            raise ValueError('depth must be in 0..12')
        size = self.size(depth)
        storage = (ctypes.c_ubyte * size)()
        written = self._lib.kernel_build(storage, size, depth)
        if written != size:
            raise RuntimeError(f'generated writer returned {written}, expected {size}')
        return TreeHandle(self, storage)
    def sum_leaves(self, packed):
        if type(packed) is not TreeHandle or packed._ops is not self:
            raise TypeError('packed handle belongs to another ConstructionOps')
        return int(self._lib.kernel_sum(packed._data, len(packed)))
    def to_python(self, packed):
        if type(packed) is not TreeHandle or packed._ops is not self:
            raise TypeError('packed handle belongs to another ConstructionOps')
        b, pos = packed.to_bytes(), 0
        def decode():
            nonlocal pos
            tag=b[pos]; pos+=1
            value=int.from_bytes(b[pos:pos+8], 'little', signed=True); pos+=8
            if tag == 0: return Leaf(value)
            if tag == 1: return Node(value, decode(), decode())
            raise ValueError('invalid constructor tag')
        out=decode()
        if pos != len(b): raise ValueError('trailing bytes')
        return out

class TreeHandle:
    __slots__ = ('_ops', '_data')
    def __init__(self, ops, data): self._ops, self._data = ops, data
    def __len__(self): return len(self._data)
    def to_bytes(self): return bytes(self._data)
