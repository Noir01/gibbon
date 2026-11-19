def main() -> int:
    size = 8
    values = [0] * size
    for i in range(size):
        values[i] = i * 3 + 1
    total = 0
    for j in range(len(values)):
        total += values[j]
    return total + values[-1]
