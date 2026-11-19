"""Evaluate 2 + 3*x - 4*x*x + x*x*x using Horner's method."""


def main() -> int:
    coefficients = [0] * 4
    coefficients[0] = 2
    coefficients[1] = 3
    coefficients[2] = -4
    coefficients[3] = 1
    x = 5
    result = 0
    for i in range(len(coefficients) - 1, -1, -1):
        result = result * x + coefficients[i]
    return result
