"""README tree, constructed in Python and summed by a native Gibbon kernel.

Run from worktree root inside shell-sequential.nix:
PYTHONPATH=python-kernels/frontend python3 python-kernels/integration/readme_bridge.py
"""
from api import compile_type
from readme_tree import Leaf, Node, Tree, mk_tree


def main():
    ops = compile_type(Tree, globals(), name='Tree', sum_constructors=('Leaf',))
    tree = mk_tree(10)
    packed = ops.pack(tree)
    print('Native leaf sum:', ops.sum_ints(packed))
    print('Python round-trip correct:', ops.unpack(packed) == tree)
    print('Generated Gibbon source:', ops.build_directory / 'module.hs')


if __name__ == '__main__':
    main()
