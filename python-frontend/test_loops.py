import unittest
from translate import translate, FrontendError


class LoopTests(unittest.TestCase):
    def test_loop_carries_multiple_sequential_accumulators(self):
        source = '''def compute(n: int) -> int:
    total = 0
    product = 1
    for i in range(n):
        total = total + i
        product = product + total
    return product + total

def main() -> int:
    return compute(6)
'''
        out = translate(source)
        self.assertIn('p_loop', out)
        self.assertNotIn('for ', out)

    def test_conditional_updates_and_negative_step(self):
        source = '''def main() -> int:
    total = 0
    for i in range(8, -2, -2):
        if i > 3:
            total = total + i * 2
        else:
            total = total - i
    return total
'''
        self.assertIn('p_loop', translate(source))

    def test_augmented_accumulator(self):
        source = 'def main() -> int:\n    total = 1\n    total *= 2\n    for i in range(6):\n        total += i\n    return total\n'
        self.assertIn('p_loop', translate(source))

    def test_reject_ambiguous_loop_behaviors(self):
        cases = [
            'for i in range(3):\n        break',
            'for i in range(3):\n        continue',
            'for i in range(3):\n        return 7',
            'for i in range(3, 7, 0):\n        total = total + i',
            'for i in range(3):\n        i = 1',
            'for i in range(3):\n        total = True',
        ]
        for loop in cases:
            with self.subTest(loop=loop):
                source = 'def main() -> int:\n    total = 0\n    ' + loop + '\n    return total\n'
                with self.assertRaises(FrontendError):
                    translate(source)
        for source in (
            'def main() -> int:\n    for i in range(0):\n        x = i\n    return x',
            'def main() -> int:\n    for i in range(3):\n        x = i\n    return i',
            'def range(n: int) -> int:\n    return n\ndef main() -> int:\n    x = 0\n    for i in range(3):\n        x = i\n    return x',
        ):
            with self.subTest(source=source):
                with self.assertRaises(FrontendError):
                    translate(source)


if __name__ == '__main__':
    unittest.main()
