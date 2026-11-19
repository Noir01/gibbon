import gc
import random
import unittest
from dataclasses import dataclass
from typing import Union
from api import compile_type

@dataclass
class Lit:
    value: int
@dataclass
class Add:
    left: 'Expr'
    right: 'Expr'
Expr = Union[Lit, Add]

@dataclass
class Tip:
    value: int
@dataclass
class Fork:
    weight: int
    left: 'WeightedTree'
    right: 'WeightedTree'
WeightedTree = Union[Tip, Fork]


def reference_sum(tree):
    if isinstance(tree, (Lit, Tip)):
        return tree.value
    return (tree.weight if isinstance(tree, Fork) else 0) + reference_sum(tree.left) + reference_sum(tree.right)


def reference_add(tree, amount):
    if isinstance(tree, (Lit, Tip)):
        return type(tree)(tree.value + amount)
    children = reference_add(tree.left, amount), reference_add(tree.right, amount)
    return Fork(tree.weight + amount, *children) if isinstance(tree, Fork) else Add(*children)


class ApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.expr_ops = compile_type(Expr, globals(), 'Expr')
        cls.weighted_ops = compile_type(WeightedTree, globals(), 'WeightedTree')

    def test_schema_driven_pack_unpack_and_validation(self):
        ops = self.expr_ops
        value = Add(Lit(-2), Lit(9))
        self.assertEqual(ops.unpack(ops.pack(value)), value)
        with self.assertRaises(TypeError): ops.pack(True)
        with self.assertRaises(TypeError): ops.unpack(b'bad')
        with self.assertRaises(TypeError): ops.pack(Lit(True))
        with self.assertRaises(OverflowError): ops.pack(Lit(1 << 63))

    def test_compile_produces_native_ops(self):
        ops = self.expr_ops
        value = ops.pack(Add(Lit(2), Lit(3)))
        self.assertEqual(ops.sum_ints(value), 5)
        output = ops.add_ints(value, 4)
        self.assertEqual(ops.sum_ints(output), 13)
        self.assertEqual(ops.unpack(output), Add(Lit(6), Lit(7)))

    def test_two_schema_libraries_alive_together(self):
        ops = self.weighted_ops
        tree = Fork(7, Tip(-2), Fork(3, Tip(5), Tip(0)))
        packed = ops.pack(tree)
        self.assertEqual(ops.sum_ints(packed), reference_sum(tree))
        updated = ops.add_ints(packed, -4)
        self.assertEqual(ops.unpack(updated), reference_add(tree, -4))
        self.assertEqual(self.expr_ops.sum_ints(self.expr_ops.pack(Lit(11))), 11)
        with self.assertRaises(TypeError): self.expr_ops.sum_ints(packed)
        with self.assertRaises(TypeError): self.expr_ops.add_ints(packed, 1)

    def test_output_outlives_input_and_repeated_transforms(self):
        ops = self.expr_ops
        tree = Add(Lit(-8), Add(Lit(20), Lit(-3)))
        packed = ops.pack(tree)
        original = packed.to_bytes()
        output = ops.add_ints(packed, 4)
        self.assertEqual(packed.to_bytes(), original)
        del packed
        gc.collect()
        output = ops.add_ints(output, -2)
        self.assertEqual(ops.unpack(output), reference_add(tree, 2))
        self.assertEqual(ops.sum_ints(output), reference_sum(reference_add(tree, 2)))

    def test_cycles_aliases_and_depth_are_rejected(self):
        ops = self.expr_ops
        leaf = Lit(1)
        with self.assertRaises(ValueError): ops.pack(Add(leaf, leaf))
        cycle = Add(Lit(1), Lit(2))
        cycle.left = cycle
        with self.assertRaises(ValueError): ops.pack(cycle)
        tree = Lit(0)
        for _ in range(130): tree = Add(tree, Lit(1))
        with self.assertRaisesRegex(ValueError, 'depth'): ops.pack(tree)

    def test_arithmetic_overflow_is_rejected_before_native_calls(self):
        ops = self.expr_ops
        maximum = (1 << 63) - 1
        with self.assertRaises(OverflowError): ops.add_ints(ops.pack(Lit(maximum)), 1)
        with self.assertRaises(OverflowError): ops.sum_ints(ops.pack(Add(Lit(maximum), Lit(1))))
        with self.assertRaises(TypeError): ops.add_ints(ops.pack(Lit(0)), True)
        with self.assertRaises(OverflowError): ops.add_ints(ops.pack(Lit(0)), 1 << 63)
        self.assertEqual(ops.sum_ints(ops.pack(Lit(-(1 << 63)))), -(1 << 63))

    def test_seeded_random_trees_against_python_reference(self):
        rng = random.Random(711)
        def tree(depth, weighted):
            if not depth or rng.random() < 0.3:
                return (Tip if weighted else Lit)(rng.randrange(-50, 51))
            left, right = tree(depth - 1, weighted), tree(depth - 1, weighted)
            return Fork(rng.randrange(-50, 51), left, right) if weighted else Add(left, right)
        for weighted, ops in ((False, self.expr_ops), (True, self.weighted_ops)):
            for _ in range(30):
                value = tree(5, weighted)
                amount = rng.randrange(-10, 11)
                packed = ops.pack(value)
                self.assertEqual(ops.sum_ints(packed), reference_sum(value))
                result = ops.add_ints(packed, amount)
                expected = reference_add(value, amount)
                self.assertEqual(ops.unpack(result), expected)
                self.assertEqual(ops.sum_ints(result), reference_sum(expected))
                self.assertEqual(ops.unpack(packed), value)

if __name__ == '__main__': unittest.main()
