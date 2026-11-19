"""Run inside the sequential shell with PYTHONPATH=python-kernels/frontend."""
from dataclasses import dataclass
from api import compile_type

@dataclass
class Lit:
    value: int

@dataclass
class Add:
    left: 'Expr'
    right: 'Expr'

Expr = Lit | Add

ops = compile_type(Expr, globals(), name='Expr')
original = Add(Lit(-8), Add(Lit(20), Lit(-3)))
packed = ops.pack(original)
print('Original native sum:', ops.sum_ints(packed))
updated = ops.add_ints(packed, amount=4)
print('Updated native sum:', ops.sum_ints(updated))
print('Unpacked:', ops.unpack(updated))
print('Original unchanged:', ops.unpack(packed) == original)
print('Generated artifacts:', ops.build_directory)
