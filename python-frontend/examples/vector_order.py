def main() -> int:
    values = [5] * 4
    before = values[0]
    values[0] = values[0] + 7
    values[-1] = values[0] * 2
    after = values[0]
    return before * 100 + after * 10 + values[-1]
