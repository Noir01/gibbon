"""Iterative Fibonacci: sequential reassignment becomes loop-carried state."""


def fibonacci(n: int) -> int:
    previous = 0
    current = 1
    for i in range(n):
        following = previous + current
        previous = current
        current = following
    return previous


def main() -> int:
    return fibonacci(20)
