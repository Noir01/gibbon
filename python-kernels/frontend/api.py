"""Small schema-driven fixed-layout Python/Gibbon integration API."""
from __future__ import annotations
import ctypes
import struct
import subprocess
from dataclasses import fields, is_dataclass
from pathlib import Path
from frontend import extract_schema, generate_source

_INT = struct.Struct('@q')
_MAX_DEPTH = 128

class Packed:
    __slots__ = ('_ops', '_data', 'total', 'minimum', 'maximum', 'count')
    def __init__(self, ops, data, total, minimum, maximum, count):
        self._ops, self._data = ops, (ctypes.c_ubyte * len(data)).from_buffer_copy(data)
        self.total, self.minimum, self.maximum, self.count = total, minimum, maximum, count
    def __len__(self): return len(self._data)
    def to_bytes(self): return bytes(self._data)

class Ops:
    def __init__(self, root_union, namespace, name, sum_constructors=None):
        self.root_union = root_union
        self.schema = extract_schema(root_union, namespace=namespace, root_name=name)
        self.types = tuple(__import__('typing').get_args(root_union)) or (root_union,)
        self.by_type = {t: i for i, t in enumerate(self.types)}
        from native_build import build
        self._library, self.build_directory = build(self.schema, sum_constructors=sum_constructors)
    def sum_ints(self, packed):
        self._check(packed)
        self._check_sum_range(packed.minimum, packed.maximum, packed.count)
        return self._library.kernel_sum(packed._data, len(packed))
    @staticmethod
    def _check_sum_range(minimum, maximum, count):
        # Conservative bound: every intermediate recursive sum must fit too.
        if count * min(0, minimum) < -(1 << 63) or count * max(0, maximum) >= (1 << 63):
            raise OverflowError('possible int64 intermediate sum overflow')
    def add_ints(self, packed, amount):
        self._check(packed)
        if type(amount) is not int:
            raise TypeError('amount must be int, not bool')
        if not -(1 << 63) <= amount < (1 << 63):
            raise OverflowError('amount outside int64')
        minimum = packed.minimum + amount if packed.count else 0
        maximum = packed.maximum + amount if packed.count else 0
        if minimum < -(1 << 63) or maximum >= (1 << 63):
            raise OverflowError('integer field would overflow int64')
        output = Packed(self, bytes(len(packed)), packed.total + amount * packed.count,
                        minimum, maximum, packed.count)
        written = self._library.kernel_add(packed._data, len(packed), amount,
                                          output._data, len(output))
        if written != len(output):
            raise RuntimeError('generated transform violated fixed-size contract')
        return output
    def pack(self, value):
        seen, vals = set(), []
        def encode(node, depth):
            if depth > _MAX_DEPTH: raise ValueError('maximum tree depth exceeded')
            typ = type(node)
            if typ not in self.by_type: raise TypeError('value must use an exact root constructor')
            if id(node) in seen: raise ValueError('cycles and repeated object identities are unsupported')
            seen.add(id(node)); constructor = self.schema.constructors[self.by_type[typ]]
            fs = fields(typ)
            if len(fs) != len(constructor.fields): raise TypeError('schema mismatch')
            out = bytearray((self.by_type[typ],))
            for f, spec in zip(fs, constructor.fields):
                val = getattr(node, f.name)
                if spec.kind == 'int':
                    if type(val) is not int: raise TypeError(f'{f.name} must be int (not bool)')
                    if not -(1 << 63) <= val < (1 << 63): raise OverflowError(f'{f.name} outside int64')
                    out.extend(_INT.pack(val)); vals.append(val)
                else: out.extend(encode(val, depth + 1))
            return bytes(out)
        data = encode(value, 0)
        return Packed(self, data, sum(vals), min(vals, default=0), max(vals, default=0), len(vals))
    def _check(self, packed):
        if not isinstance(packed, Packed) or packed._ops is not self: raise TypeError('handle belongs to another ops instance')
    def unpack(self, packed):
        self._check(packed); data = packed.to_bytes(); pos = 0
        def decode(depth):
            nonlocal pos
            if depth > _MAX_DEPTH or pos >= len(data): raise ValueError('truncated or too-deep packed value')
            tag = data[pos]; pos += 1
            if tag >= len(self.types): raise ValueError('invalid constructor tag')
            typ = self.types[tag]; args = []
            for spec in self.schema.constructors[tag].fields:
                if spec.kind == 'int':
                    if pos + 8 > len(data): raise ValueError('truncated integer')
                    args.append(_INT.unpack_from(data, pos)[0]); pos += 8
                else: args.append(decode(depth + 1))
            return typ(*args)
        result = decode(0)
        if pos != len(data): raise ValueError('trailing packed bytes')
        return result

def compile_type(root_union, namespace, name=None, *, sum_constructors=None):
    """Generate and compile restricted kernels; invoke inside the sequential Nix shell."""
    return Ops(root_union, namespace, name, sum_constructors=sum_constructors)
