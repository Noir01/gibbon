"""Ordinary executable Python; also input to the restricted frontend."""
from dataclasses import dataclass


@dataclass
class Leaf:
    value: int


@dataclass
class Node:
    label: int
    left: "Tree"
    right: "Tree"


Tree = Leaf | Node


def build(depth: int) -> Tree:
    if depth <= 0:
        return Leaf(3)
    else:
        left = build(depth - 1)
        right = build(depth - 1)
        return Node(depth, left, right)


def shift(tree: Tree, amount: int) -> Tree:
    match tree:
        case Leaf(value):
            return Leaf(value + amount)
        case Node(label, left, right):
            return Node(label, shift(left, amount), shift(right, amount))


def sum_leaves(tree: Tree) -> int:
    match tree:
        case Leaf(value):
            return value
        case Node(_, left, right):
            return sum_leaves(left) + sum_leaves(right)


def main() -> int:
    tree = build(5)
    changed = shift(tree, 4)
    return sum_leaves(changed)
