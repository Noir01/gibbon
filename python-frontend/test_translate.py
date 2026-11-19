"""Stdlib-only source frontend tests. Run: python3 -m unittest -v."""
import unittest
import pathlib
import subprocess
import sys
import tempfile
from translate import translate, FrontendError


class TranslationTests(unittest.TestCase):
    def test_scalar_source_and_mangling(self):
        out = translate('def main() -> int:\n    case = 7\n    return case * 3 - 2\n')
        self.assertIn('p_main :: Int', out)
        self.assertIn('let p_case', out)
        self.assertIn('((p_case * 3) - 2)', out)
        self.assertIn('gibbon_main = p_main', out)
        other = translate('def main() -> int:\n    return 91 + 4\n')
        self.assertIn('(91 + 4)', other)
        self.assertNotEqual(out, other)

    def test_helpers_conditionals_shadowing_and_boolean(self):
        source = '''def choose(n: int) -> int:
    n = n + 1
    if n >= 8:
        return -n
    else:
        return choose(n + 2)
def main() -> bool:
    return choose(2) == -9
'''
        out = translate(source)
        self.assertIn('p_choose :: Int -> Int', out)
        self.assertIn('if ', out)
        self.assertIn(' >= 8)', out)
        self.assertIn('p_choose (', out)
        self.assertIn('p_main :: Bool', out)
        # A recursive Haskell let must not capture its own RHS.
        self.assertNotIn('let p_n = (p_n + 1)', out)
        with self.assertRaisesRegex(FrontendError, 'return type mismatch'):
            translate('def main() -> bool:\n    return 3\n')

    def test_recursive_adt_match_and_helper_result(self):
        source = '''from dataclasses import dataclass
@dataclass
class Leaf:
    value: int
@dataclass
class Node:
    flag: bool
    left: "Tree"
    right: "Tree"
@dataclass
class Empty:
    pass
Tree = Leaf | Node | Empty
def make(n: int) -> Tree:
    return Node(True, Leaf(n), Empty())
def score(t: Tree) -> int:
    match t:
        case Leaf(x):
            return x * 5
        case Node(flag, left, _):
            if flag:
                return score(left) + 11
            else:
                return 0
        case Empty():
            return -2
def main() -> int:
    return score(make(8))
'''
        out = translate(source)
        self.assertIn('data Tree = Leaf Int | Node Bool Tree Tree | Empty', out)
        self.assertIn('p_make :: Int -> Tree', out)
        self.assertIn('case p_t of', out)
        self.assertIn('Leaf p_x ->', out)
        self.assertIn('Node p_flag p_left _ ->', out)
        self.assertIn('(p_x * 5)', out)
        with self.assertRaisesRegex(FrontendError, 'nonexhaustive'):
            translate(source.replace('        case Empty():\n            return -2\n', ''))

    def test_strict_rejections_are_source_located(self):
        bad_sources = [
            'import os\ndef main() -> int:\n    return 0',
            'from dataclasses import dataclass as dc\ndef main() -> int:\n    return 0',
            'def main(x: int = 3) -> int:\n    return x',
            'def helper(x: int = 3) -> int:\n    return x\ndef main() -> int:\n    return helper()',
            'def helper(*x: int) -> int:\n    return 0\ndef main() -> int:\n    return 0',
            '@oops\ndef main() -> int:\n    return 0',
            'def main() -> int:\n    def inner() -> int:\n        return 0\n    return inner()',
            'def main() -> int:\n    x = 1\n    x /= 2\n    return x',
            'def main() -> int:\n    x = 1\n    x.a = 2\n    return x',
            'def main() -> int:\n    for x in range(3):\n        pass\n    return 0',
            'def main() -> int:\n    return mystery()',
            'def main() -> int:\n    return missing',
            'def main() -> int:\n    return True + 2',
            'def main() -> int:\n    return 1\n    return 2',
            'def main() -> int:\n    if 1:\n        return 2\n    else:\n        return 3',
            'def f(x: int) -> int:\n    return x\ndef main() -> int:\n    return f(True)',
            'def main() -> int:\n    return 1\ndef main() -> int:\n    return 2',
            'def main() -> int:\n    return 1 < 2 < 3',
            'def main() -> int:\n    return 1 / 2',
            'def main() -> int:\n    return "text"',
            'def main() -> int:\n    return 1\n# type: ignore',
            'def broken(',
            '',
        ]
        for source in bad_sources:
            with self.subTest(source=source):
                with self.assertRaisesRegex(FrontendError, r'bad.py:\d+:\d+:'):
                    translate(source, 'bad.py')

    def test_reject_adt_layout_and_patterns(self):
        prefix = '''from dataclasses import dataclass
@dataclass
class Leaf:
    n: int
@dataclass
class Node:
    t: "Tree"
Tree = Leaf | Node
'''
        suffix = '''def f(t: Tree) -> int:
    match t:
        case Leaf(n):
            return n
        case Node(t):
            return f(t)
def main() -> int:
    return f(Leaf(7))
'''
        for source in [
            prefix.replace('    t: "Tree"', '    t: "Tree"\n    n: int') + suffix,
            prefix.replace('@dataclass', '@dataclass()') + suffix,
            prefix.replace('n: int', 'n: int = 1') + suffix,
            prefix.replace('Tree = Leaf | Node', 'Tree = Leaf | Missing') + suffix,
            prefix + suffix.replace('case Leaf(n):', 'case Leaf(n) if n > 0:'),
            prefix + suffix.replace('case Leaf(n):', 'case Leaf(n= n):'),
            prefix + suffix.replace('case Leaf(n):', 'case Leaf(1):'),
            prefix + suffix.replace('case Leaf(n):', 'case Leaf(n, x):'),
            prefix + suffix.replace('case Leaf(n):', 'case _:'),
            prefix + suffix.replace('return n', 'return t + 1'),
            prefix + suffix.replace('f(Leaf(7))', 'f(Node(7))'),
        ]:
            with self.subTest(source=source):
                with self.assertRaises(FrontendError):
                    translate(source)

    def test_cli_writes_translation_and_reports_error(self):
        with tempfile.TemporaryDirectory() as directory:
            src = pathlib.Path(directory) / 'input.py'
            dst = pathlib.Path(directory) / 'output.hs'
            source = 'def main() -> bool:\n    return False\n'
            src.write_text(source)
            command = [sys.executable, str(pathlib.Path(__file__).with_name('translate.py')), str(src), '-o', str(dst)]
            result = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(dst.exists(), 'CLI must create output')
            self.assertEqual(dst.read_text(), translate(source, str(src)))
            src.write_text('import os')
            result = subprocess.run(command, capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(str(src) + ':1:1:', result.stderr)
            self.assertNotIn('Traceback', result.stderr)

    def test_docstrings_and_literal_range(self):
        source = '\"\"\"Module docs.\"\"\"\ndef main() -> int:\n    \"\"\"Function docs.\"\"\"\n    return 17\n'
        self.assertIn('p_main = 17', translate(source))
        for literal in ('9223372036854775808', '-9223372036854775809'):
            with self.subTest(literal=literal):
                with self.assertRaisesRegex(FrontendError, '64-bit'):
                    translate('def main() -> int:\n    return ' + literal)
        self.assertIn('9223372036854775807', translate('def main() -> int:\n    return -9223372036854775808'))

    def test_no_ignored_metadata_or_invalid_identifiers(self):
        for source in [
            'def main() -> int:\n    x = 1 # type: int\n    return x',
            'def café() -> int:\n    return 1\ndef main() -> int:\n    return café()',
            'def main() -> int:\n    café = 1\n    return café',
            'def main(x, /) -> int:\n    return 1',
            'def main() -> int:\n    pass',
        ]:
            with self.subTest(source=source):
                with self.assertRaises(FrontendError):
                    translate(source)


if __name__ == '__main__':
    unittest.main()
