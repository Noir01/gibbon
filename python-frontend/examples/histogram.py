"""Build category data, then count it using data-dependent vector indices."""


def main() -> int:
    samples = [0] * 12
    for i in range(len(samples)):
        if i < 4:
            samples[i] = 0
        else:
            if i < 9:
                samples[i] = 1
            else:
                samples[i] = 2
    counts = [0] * 3
    for j in range(len(samples)):
        category = samples[j]
        counts[category] = counts[category] + 1
    # Encode three single-digit counts into one scalar result.
    return counts[0] + 10 * counts[1] + 100 * counts[2]
