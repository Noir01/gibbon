import unittest
from dataclasses import dataclass, FrozenInstanceError
from typing import Union
from frontend import extract_schema, generate_source

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

class FrontendTests(unittest.TestCase):
    def test_records_are_frozen_and_nested_fields_are_tuples(self):
        schema = extract_schema(Expr, namespace=globals())
        with self.assertRaises(FrozenInstanceError): schema.name = 'Changed'
        with self.assertRaises(FrozenInstanceError): schema.constructors[0].name = 'Changed'
        self.assertIsInstance(schema.constructors, tuple)
        self.assertIsInstance(schema.constructors[0].fields, tuple)

    def test_expr_schema_and_generation(self):
        source = generate_source(extract_schema(Expr, namespace=globals()))
        self.assertIn('data Expr = Lit Int | Add Expr Expr', source)
        self.assertIn('amount', source)

    def test_mixed_integer_and_recursion(self):
        source = generate_source(extract_schema(WeightedTree, namespace=globals()))
        self.assertIn('Fork Int WeightedTree WeightedTree', source)
        self.assertIn('Fork (f0 + amount)', source)

    def test_reject_bool(self):
        @dataclass
        class Bad: flag: bool
        with self.assertRaisesRegex(TypeError, 'unsupported.*flag'):
            extract_schema(Bad, namespace=globals())

    def test_postponed_annotations_resolve_int_and_recursive_alias(self):
        ns = {}
        exec("from __future__ import annotations\nfrom dataclasses import dataclass\nfrom typing import Union\n@dataclass\nclass Node:\n value: int\n child: 'Tree'\nTree = Union[Node]", ns)
        schema = extract_schema(ns['Tree'], namespace=ns)
        self.assertEqual([f.kind for f in schema.constructors[0].fields], ['int', 'recursive'])

    def test_same_named_foreign_class_is_not_recursive(self):
        Foreign = type('Expr', (), {})
        @dataclass
        class Holder: child: Foreign
        with self.assertRaisesRegex(TypeError, 'unsupported.*child'):
            extract_schema(Holder, namespace=globals())

    def test_reject_invalid_or_duplicate_constructor_names(self):
        from frontend import Schema, Constructor
        with self.assertRaisesRegex(ValueError, 'invalid Haskell constructor'):
            generate_source(Schema('Root', [Constructor('lowercase', [])]))
        with self.assertRaisesRegex(ValueError, 'duplicate constructor'):
            generate_source(Schema('Root', [Constructor('Same', []), Constructor('Same', [])]))

    def test_signatures_and_deterministic_nullary_unary_generation(self):
        from frontend import Schema, Constructor, SchemaField
        schema = Schema('Root', [Constructor('Empty', []), Constructor('One', [SchemaField('x', 'int')])])
        source = generate_source(schema)
        self.assertIn('sum_ints :: Root -> Int', source)
        self.assertIn('add_ints :: Root -> Int -> Root', source)
        self.assertEqual(source, generate_source(schema))

    def test_reject_unresolved_recursive_reference(self):
        @dataclass
        class Lost: child: 'Missing'
        with self.assertRaisesRegex(TypeError, 'unresolved.*Missing'):
            extract_schema(Lost, namespace={})

if __name__ == '__main__': unittest.main()
