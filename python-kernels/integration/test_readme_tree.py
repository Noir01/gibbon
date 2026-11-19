import unittest
from readme_tree import Leaf, Node, mk_tree, sum_tree

class ReadmeTreeTests(unittest.TestCase):
    def test_base_case(self):
        self.assertEqual(mk_tree(0), Leaf(1))
        self.assertEqual(mk_tree(-3), Leaf(1))

    def test_constructor_keeps_depth(self):
        self.assertEqual(mk_tree(1), Node(1, Leaf(1), Leaf(1)))
        tree = mk_tree(2)
        self.assertIsNot(tree.left, tree.right)

    def test_sum_ignores_internal_node_values(self):
        self.assertEqual(sum_tree(Node(999, Leaf(2), Leaf(3))), 5)

    def test_readme_depth(self):
        self.assertEqual(sum_tree(mk_tree(10)), 1 << 10)

if __name__ == '__main__':
    unittest.main()
