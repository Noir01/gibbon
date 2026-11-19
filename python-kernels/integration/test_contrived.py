import unittest
from contrived_poc import run_demo


class ContrivedTests(unittest.TestCase):
    def test_generated_kernels_match_python_reference(self):
        run_demo()


if __name__ == '__main__':
    unittest.main()
