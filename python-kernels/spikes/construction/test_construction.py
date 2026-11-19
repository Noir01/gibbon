import unittest
from construction import ConstructionOps, Leaf, Node
from readme_tree import mk_tree, sum_tree, Tree
from api import compile_type

class ConstructionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ops=ConstructionOps()
        cls.oracle=compile_type(Tree, vars(__import__('readme_tree')), name='Tree', sum_constructors=('Leaf',))
    def test_shallow_layout_and_python_codec(self):
        for depth in (0,1):
            packed=self.ops.build_tree(depth)
            expected=self.oracle.pack(mk_tree(depth)).to_bytes()
            self.assertEqual(packed.to_bytes(), expected)
            self.assertEqual(self.ops.to_python(packed), mk_tree(depth))
    def test_depth10_native_sum(self):
        packed=self.ops.build_tree(10)
        self.assertEqual(self.ops.sum_leaves(packed), sum_tree(mk_tree(10)))
        self.assertEqual(self.ops.sum_leaves(packed), 1024)
    def test_oracle_layout_representative_depths(self):
        for depth in (2,5):
            self.assertEqual(self.ops.build_tree(depth).to_bytes(), self.oracle.pack(mk_tree(depth)).to_bytes())
    def test_independent_storage_and_repeated_builds(self):
        a=self.ops.build_tree(5); before=a.to_bytes()
        b=self.ops.build_tree(2)
        self.assertEqual(a.to_bytes(), before)
        self.assertNotEqual(a._data, b._data)
    def test_validation_before_writer(self):
        lib=self.ops._lib
        for value in (-1,13):
            with self.assertRaises(ValueError): self.ops.build_tree(value)
        for value in (True, 1.0, '2'):
            with self.assertRaises(TypeError): self.ops.build_tree(value)
        buf=(__import__('ctypes').c_ubyte*8)()
        self.assertEqual(lib.kernel_build(buf, 8, 1), -1)

if __name__ == '__main__': unittest.main()
