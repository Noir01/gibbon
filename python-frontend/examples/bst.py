"""Persistent BST insertion, with a tree carried through an ordinary for-loop."""
from dataclasses import dataclass


@dataclass
class Empty:
    pass


@dataclass
class Branch:
    key: int
    left: "SearchTree"
    right: "SearchTree"


SearchTree = Empty | Branch


def insert(tree: SearchTree, value: int) -> SearchTree:
    match tree:
        case Empty():
            return Branch(value, Empty(), Empty())
        case Branch(key, left, right):
            if value < key:
                return Branch(key, insert(left, value), right)
            else:
                if value > key:
                    return Branch(key, left, insert(right, value))
                else:
                    return Branch(key, left, right)


def total(tree: SearchTree) -> int:
    match tree:
        case Empty():
            return 0
        case Branch(key, left, right):
            return key + total(left) + total(right)


def main() -> int:
    tree = Empty()
    for i in range(10):
        tree = insert(tree, i)
    # Re-inserting an existing key must not change the set.
    tree = insert(tree, 5)
    return total(tree)
