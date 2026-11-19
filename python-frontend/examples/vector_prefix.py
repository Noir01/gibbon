def main() -> int:
    values = [1] * 6
    for i in range(1, 6):
        values[i] = values[i - 1] + i
    total = 0
    for j in range(len(values)):
        total += values[j]
    return total
