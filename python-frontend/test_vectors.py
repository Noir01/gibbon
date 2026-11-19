import unittest
from translate import translate, FrontendError


class VectorTests(unittest.TestCase):
    def test_local_list_fill_and_sum(self):
        source = '''def main() -> int:
    size = 8
    values = [0] * size
    for i in range(size):
        values[i] = i * 3 + 1
    total = 0
    for j in range(len(values)):
        total += values[j]
    return total + values[-1]
'''
        out = translate(source)
        self.assertIn('Vector Int', out)
        self.assertIn('vec :: Vector Int; vec = valloc', out)
        self.assertIn('inplacevupdate', out)
        self.assertIn('vnth', out)
        self.assertIn('vlength', out)

    def test_integer_list_literals(self):
        source = '''def increment(x: int) -> int:
    return x + 1

def main() -> int:
    base = 4
    values = [increment(base), -2, base * 3]
    values[1] = values[0] + values[2]
    return values[1] + len(values)
'''
        out = translate(source)
        self.assertIn('valloc 3', out)
        self.assertIn('inplacevupdate', out)
        self.assertIn('Vector Int', out)
        self.assertIn('valloc 0', translate('def main() -> int:\n    values = []\n    return len(values)'))

    def test_reject_noninteger_literals(self):
        for literal in ('[1, True]', '[[1], [2]]', '[1, "two"]', '[x for x in range(3)]'):
            with self.subTest(literal=literal):
                with self.assertRaises(FrontendError):
                    translate('def main() -> int:\n    values = ' + literal + '\n    return 0')

    def test_unsupported_list_behaviors(self):
        for statement in (
            'alias = values',
            'values.append(3)',
            'values[0] = True',
            'values[0:1] = 4',
        ):
            with self.subTest(statement=statement):
                with self.assertRaises(FrontendError):
                    translate('def main() -> int:\n    values = [0] * 3\n    ' + statement + '\n    return 0')
        with self.assertRaises(FrontendError):
            translate('def main() -> int:\n    values = [1, True]\n    return 0')


if __name__ == '__main__':
    unittest.main()
