"""Illustrative decision tree: packed recursive model + external feature vector.

This is a hand-written test model, not a trained predictor. Threshold equality
chooses the left child. Target arithmetic is Gibbon Float (32-bit), not Python's
64-bit float. Feature vectors passed to user functions are read-only.
"""
from dataclasses import dataclass


@dataclass
class Leaf:
    value: float


@dataclass
class Split:
    feature: int
    threshold: float
    left: "Tree"
    right: "Tree"


Tree = Leaf | Split


def predict(tree: Tree, features: list[float]) -> float:
    match tree:
        case Leaf(value):
            return value
        case Split(feature, threshold, left, right):
            if features[feature] <= threshold:
                return predict(left, features)
            else:
                return predict(right, features)


def model() -> Tree:
    return Split(0, 1.5, Split(1, -0.5, Leaf(-1.25), Leaf(2.5)), Leaf(4.75))


def main() -> float:
    tree = model()
    features = [1.0, 0.0]
    return predict(tree, features)
