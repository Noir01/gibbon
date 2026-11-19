"""Self-contained Python datatype demo of the generated Gibbon bridge."""
from dataclasses import dataclass

from api import compile_type


@dataclass
class Leaf:
    value: int


@dataclass
class Node:
    value: int
    left: "Tree"
    right: "Tree"


Tree = Leaf | Node


def mk_tree(depth: int) -> Tree:
    if depth <= 0:
        return Leaf(1)
    left = mk_tree(depth - 1)
    right = mk_tree(depth - 1)
    return Node(depth, left, right)

tree = Node(
    value=10,
    left=Leaf(
        value=10,
    ),
    right=Leaf(
        value=10,
    )
)


def main():
    ops = compile_type(
        Tree,
        globals(),
        name="Tree",
        sum_constructors=("Leaf",),
    )
    python_tree = mk_tree(10)
    packed_tree = ops.pack(tree)
    total = ops.sum_ints(packed_tree)
    print("Native leaf sum:", total)
    restored_tree = ops.unpack(packed_tree)
    print("Round-trip correct:", restored_tree == tree)
    print("Generated Gibbon source:", ops.build_directory / "module.hs")


if __name__ == "__main__":
    main()
