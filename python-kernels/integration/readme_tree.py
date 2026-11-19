"""Sequential Python equivalent of the Gibbon README tree example.

sum_tree intentionally ignores Node.value, matching the supplied Haskell.
The prototype's native sum_ints sums ALL integer fields and is not equivalent.
"""
from dataclasses import dataclass

@dataclass
class Leaf:
    value: int

@dataclass
class Node:
    value: int
    left: 'Tree'
    right: 'Tree'

Tree = Leaf | Node


def mk_tree(i: int) -> Tree:
    if i <= 0:
        return Leaf(1)
    left = mk_tree(i - 1)
    right = mk_tree(i - 1)
    return Node(i, left, right)


def sum_tree(tree: Tree) -> int:
    match tree:
        case Leaf(value):
            return value
        case Node(_, left, right):
            return sum_tree(left) + sum_tree(right)
        case _:
            raise TypeError('expected Leaf or Node')


if __name__ == '__main__':
    print(sum_tree(mk_tree(10)))
