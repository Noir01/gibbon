"""An interpreter with four constructors and conditional evaluation."""
from dataclasses import dataclass


@dataclass
class Literal:
    value: int


@dataclass
class Plus:
    left: "Expr"
    right: "Expr"


@dataclass
class Times:
    left: "Expr"
    right: "Expr"


@dataclass
class Choose:
    condition: "Expr"
    positive: "Expr"
    otherwise: "Expr"


Expr = Literal | Plus | Times | Choose


def evaluate(expression: Expr) -> int:
    match expression:
        case Literal(value):
            return value
        case Plus(left, right):
            return evaluate(left) + evaluate(right)
        case Times(left, right):
            return evaluate(left) * evaluate(right)
        case Choose(condition, positive, otherwise):
            if evaluate(condition) > 0:
                return evaluate(positive)
            else:
                return evaluate(otherwise)


def main() -> int:
    expression = Choose(
        Plus(Literal(3), Literal(-1)),
        Times(Plus(Literal(4), Literal(5)), Literal(7)),
        Literal(-999),
    )
    return evaluate(expression)
