def descending(n: int) -> bool:
    if n <= 0:
        return True
    else:
        return descending(n - 1)


def main() -> bool:
    return descending(8)
