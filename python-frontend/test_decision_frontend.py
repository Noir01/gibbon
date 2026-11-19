"""Restricted float and borrowed-vector source frontend tests (no native build)."""
import unittest
from translate import FrontendError, translate


class DecisionFrontendTests(unittest.TestCase):
    def test_float_scalars_and_operators(self):
        out = translate('''def score(x: float) -> float:
    return -x + 2.5 * x - 0.25
def main() -> float:
    return score(1.25)
''')
        self.assertIn('p_score :: Float -> Float', out)
        self.assertIn('p_main :: Float', out)
        for op in ('.+.', '.-.', '.*.'):
            self.assertIn(op, out)
        for op, emitted in (('==', '.==.'), ('<', '.<.'), ('>', '.>.'), ('<=', '.<=.'), ('>=', '.>=.')):
            with self.subTest(op=op):
                out = translate(f'def main() -> bool:\n    return 1.25 {op} 2.5\n')
                self.assertIn(emitted, out)
        out = translate('def main() -> bool:\n    return 1.0 != 2.0\n')
        self.assertIn('if (1.0 .==. 2.0) then False else True', out)

    def test_float_negation_preserves_signed_zero(self):
        out = translate('def negate(x: float) -> float:\n    return -x\ndef main() -> float:\n    return negate(0.0)')
        # 0.0 - x loses the sign when x is +0.0; negate with exact -1.
        self.assertIn('((0.0 .-. 1.0) .*. p_x)', out)

    def test_float32_literal_limits_and_underflow_policy(self):
        # The emitter preserves decimal spelling; the target rounds to binary32,
        # including gradual underflow/round-to-zero. This is not float64 math.
        for literal in ('3.4028234663852886e38', '-3.4028234663852886e38',
                        '1e-45', '1e-100', '0.0', '-0.0'):
            with self.subTest(literal=literal):
                self.assertIn('p_main :: Float', translate(f'def main() -> float:\n    return {literal}'))
        for literal in ('3.402823466385289e38', '-1e400'):
            with self.assertRaisesRegex(FrontendError, 'finite float32 range'):
                translate(f'def main() -> float:\n    return {literal}')

    def test_local_float_vectors_and_monomorphic_helpers(self):
        out = translate('''def main() -> float:
    values = [1.25, -2.5, 0.0]
    repeated = [0.5] * 3
    ints = [0] * 2
    for i in range(len(values)):
        repeated[i] = values[i] + repeated[i]
    values[-1] = repeated[0]
    return values[-1]
''')
        self.assertIn(':: Vector Float;', out)
        self.assertIn('Float -> Int -> Vector Float', out)
        self.assertIn('Vector Float -> Int -> Int', out)
        self.assertIn('Vector Int -> Int -> Int', out)
        self.assertIn('Int -> Int -> Float -> Vector Float -> Vector Float', out)
        self.assertIn('raw < 0 then raw + size', out)
        self.assertIn('list index out of bounds', out)
        self.assertIn(':: Vector Int;', translate('def main() -> int:\n    x = []\n    return len(x)'))

    def test_float_vector_rejections(self):
        for statement in ('x = [1, 2.0]', 'x = [1.0, True]', 'x = [[1.0]]',
                          'x = [0.0] * 2.0', 'x = [True] * 2',
                          'x = [1.0]\n    y = x',
                          'x = [1.0]\n    x[0] = 1',
                          'x = [1]\n    x[0] = 1.0'):
            with self.subTest(statement=statement):
                with self.assertRaises(FrontendError):
                    translate('def main() -> int:\n    ' + statement + '\n    return 0')

    def test_readonly_vector_helpers_and_caller_mutation(self):
        for element, literal in (('int', '1'), ('float', '1.0')):
            with self.subTest(element=element):
                out = translate(f'''def first(xs: list[{element}]) -> {element}:
    return xs[-1]
def forward(xs: list[{element}]) -> {element}:
    return first(xs)
def main() -> {element}:
    xs = [{literal}]
    before = forward(xs)
    xs[0] = before + {literal}
    return xs[0]
''')
                typ = element.capitalize()
                self.assertIn(f'p_first :: Vector {typ} -> {typ}', out)
                self.assertIn(f'p_forward :: Vector {typ} -> {typ}', out)
                self.assertIn('inplacevupdate', out)

    def test_borrowed_vectors_reject_mutation_rebinding_and_aliases(self):
        for element, literal in (('int', '1'), ('float', '1.0')):
            for statement in (f'xs[0] = {literal}', f'xs = [{literal}]',
                              'xs = []', 'xs = 0', 'alias = xs', 'xs = xs',
                              f'for i in range(1):\n        xs[0] = {literal}',
                              f'for i in range(1):\n        xs = [{literal}]',
                              'for i in range(1):\n        alias = xs'):
                with self.subTest(element=element, statement=statement):
                    message = 'aliases' if 'alias = xs' in statement else 'read-only'
                    with self.assertRaisesRegex(FrontendError, message):
                        translate(f'def bad(xs: list[{element}]) -> int:\n    {statement}\n    return 0\ndef main() -> int:\n    return bad([{literal}])')

    def test_all_vector_parameters_readonly_even_indirect_or_unused(self):
        for element, literal in (('int', '1'), ('float', '1.0')):
            source = f'''def writer(xs: list[{element}]) -> int:
    xs[0] = {literal}
    return 0
def forward(xs: list[{element}]) -> int:
    return writer(xs)
def main() -> int:
    return forward([{literal}])
'''
            with self.assertRaisesRegex(FrontendError, 'read-only'):
                translate(source)
            with self.assertRaisesRegex(FrontendError, 'read-only'):
                translate(source.replace(f'return forward([{literal}])', 'return 0'))

    def test_borrowed_vector_loop_reduction(self):
        out = translate('''def total(xs: list[float]) -> float:
    result = 0.0
    for i in range(len(xs)):
        result += xs[i]
    return result
def main() -> float:
    return total([1.0, 2.0])
''')
        self.assertIn('Vector Float -> Float -> Float', out)
        self.assertIn('.+.', out)

    def test_recursive_float_decision_tree_source(self):
        source = '''from dataclasses import dataclass
@dataclass
class Leaf:
    value: float
@dataclass
class Split:
    feature: int
    threshold: float
    left: "Tree"
    right: "Tree"
Tree = Leaf | Split
def predict(tree: Tree, features: list[float]) -> float:
    match tree:
        case Leaf(value):
            return value
        case Split(feature, threshold, left, right):
            if features[feature] <= threshold:
                return predict(left, features)
            else:
                return predict(right, features)
def main() -> float:
    tree = Split(-1, 0.5, Leaf(-1.25), Split(0, 2.0, Leaf(3.0), Leaf(4.0)))
    features = [1.0, 0.5]
    return predict(tree, features)
'''
        out = translate(source)
        self.assertIn('data Tree = Leaf Float | Split Int Float Tree Tree', out)
        self.assertIn('p_predict :: Tree -> Vector Float -> Float', out)
        self.assertIn('.<=.', out)
        self.assertIn('(p_predict (p_left) (p_features))', out)
        for replacement in ('features[0] = 1.0\n            return value',
                            'features = [1.0]\n            return value'):
            with self.assertRaises(FrontendError):
                translate(source.replace('return value', replacement))
        with self.assertRaises(FrontendError):
            translate(source.replace('case Leaf(value):', 'case Leaf(features):'))

    def test_reject_vector_fields_results_and_bad_annotations(self):
        for annotation in ('list[int]', 'list[float]', 'list[list[float]]', 'list[bool]', 'list', 'object'):
            with self.subTest(annotation=annotation):
                with self.assertRaises(FrontendError):
                    translate(f'def bad() -> {annotation}:\n    return []\ndef main() -> int:\n    return 0')
                with self.assertRaises(FrontendError):
                    translate(f'''from dataclasses import dataclass
@dataclass
class Leaf:
    values: {annotation}
@dataclass
class Empty:
    pass
Tree = Leaf | Empty
def main() -> int:
    return 0
''')
        for annotation in ('list[list[float]]', 'list[bool]', 'list', 'object'):
            with self.assertRaises(FrontendError):
                translate(f'def bad(xs: {annotation}) -> int:\n    return 0\ndef main() -> int:\n    return 0')
        with self.assertRaises(FrontendError):
            translate('def f(xs: list[float]) -> float:\n    return xs[0]\ndef main() -> float:\n    return f([])')

    def test_float_rejections(self):
        for expression in ('1.0 + 1', '1 + 1.0', 'True * 1.0', '1.0 / 2.0', '1e400', '3.5e38', '-3.5e38'):
            with self.subTest(expression=expression):
                with self.assertRaises(FrontendError):
                    translate(f'def main() -> float:\n    return {expression}\n')
        with self.assertRaises(FrontendError):
            translate('def main() -> bool:\n    return 1.0 == 1\n')


if __name__ == '__main__':
    unittest.main()
