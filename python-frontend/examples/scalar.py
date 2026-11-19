def factorial(n: int) -> int:
    if n <= 1:
        return 1
    else:
        return n * factorial(n - 1)


def main() -> int:
    return factorial(7) - factorial(3)
