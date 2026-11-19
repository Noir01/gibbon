def main() -> int:
    total = 0
    for i in range(8, -2, -2):
        if i > 3:
            total += i * 2
        else:
            total -= i
    other = 1
    for j in range(3):
        other *= 2
    return total + other
