"""Integer list literals become fixed-size Gibbon vectors."""


def increment(value: int) -> int:
    return value + 1


def main() -> int:
    base = 4
    values = [increment(base), -2, base * 3]
    values[1] = values[0] + values[-1]
    total = 0
    for i in range(len(values)):
        total += values[i]
    return total
