def accumulate(n: int) -> int:
    total = 0
    running = 1
    for i in range(n):
        total += i
        running += total
    return running + total


def main() -> int:
    return accumulate(6)
