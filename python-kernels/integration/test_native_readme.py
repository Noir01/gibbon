import unittest
from api import compile_type
from readme_tree import Leaf, Node, Tree, mk_tree, sum_tree

class NativeReadmeTests(unittest.TestCase):
    def test_readme_leaf_sum_runs_through_bridge(self):
        ops = compile_type(Tree, vars(__import__('readme_tree')), name='Tree',
                           sum_constructors=('Leaf',))
        tree = mk_tree(10)
        packed = ops.pack(tree)
        self.assertEqual(ops.sum_ints(packed), sum_tree(tree))
        self.assertEqual(ops.sum_ints(packed), 1 << 10)
        self.assertEqual(ops.unpack(packed), tree)
        special = ops.pack(Node(999, Leaf(2), Leaf(3)))
        self.assertEqual(ops.sum_ints(special), 5)
        shifted = ops.add_ints(special, 1)
        self.assertEqual(ops.sum_ints(shifted), 7)
        self.assertEqual(ops.unpack(shifted), Node(1000, Leaf(3), Leaf(4)))

    def test_unknown_constructor_is_rejected_before_build(self):
        with self.assertRaisesRegex(ValueError, 'unknown.*Missing'):
            compile_type(Tree, vars(__import__('readme_tree')), name='Tree',
                         sum_constructors=('Missing',))

if __name__ == '__main__': unittest.main()
