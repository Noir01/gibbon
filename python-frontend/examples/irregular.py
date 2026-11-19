from dataclasses import dataclass


@dataclass
class Pair:
    first: int
    second: int


@dataclass
class Wrap:
    weight: int
    child: "Weird"


@dataclass
class Fork:
    bias: int
    left: "Weird"
    middle: "Weird"
    right: "Weird"


Weird = Pair | Wrap | Fork


def score(value: Weird) -> int:
    match value:
        case Pair(a, b):
            if a > b:
                return a - b
            else:
                return b - a
        case Wrap(weight, child):
            return weight * score(child)
        case Fork(bias, left, middle, right):
            return bias + score(left) - score(middle) + score(right)


def change(value: Weird, amount: int) -> Weird:
    match value:
        case Pair(a, b):
            return Pair(a + amount, b - amount)
        case Wrap(weight, child):
            return Wrap(weight, change(child, amount))
        case Fork(bias, left, middle, right):
            return Fork(bias, change(left, amount), change(middle, amount), change(right, amount))


def main() -> int:
    tree = Fork(11, Pair(3, 9), Wrap(2, Pair(8, 1)), Pair(-4, 7))
    result = change(tree, 3)
    return score(result)
