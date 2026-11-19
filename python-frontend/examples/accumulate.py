"""Return the accumulator, not the unsupported post-loop induction variable."""


def main() -> int:
    total = 0
    for i in range(10):
        total = total + i
    return total
