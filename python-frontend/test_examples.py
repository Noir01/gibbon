"""Runnable demo programs also exercise the translation path."""
from pathlib import Path
import runpy
import unittest
from translate import translate


class DemoTests(unittest.TestCase):
    def test_vector_and_accumulator_demos(self):
        root = Path(__file__).resolve().parent / 'examples'
        for name, expected in [('vector_postfix', 19), ('vector_paths', 6), ('accumulate', 45)]:
            with self.subTest(name=name):
                path = root / (name + '.py')
                self.assertEqual(runpy.run_path(str(path))['main'](), expected)
                output = translate(path.read_text(), str(path))
                self.assertIn('gibbon_main = p_main', output)
                if name.startswith('vector_'):
                    self.assertIn('inplacevupdate', output)
                    self.assertIn('vnth', output)
