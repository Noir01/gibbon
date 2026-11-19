"""Count paths to step 7, taking 1 or 2 steps, without landing on step 3.

ways[i] stores the number of paths ending at step i. Each iteration reads
previously computed entries: a small dynamic-programming algorithm.
"""


def main() -> int:
    blocked = [0, 0, 0, 1, 0, 0, 0, 0]
    ways = [0] * len(blocked)
    ways[0] = 1
    for i in range(1, len(blocked)):
        if blocked[i] == 1:
            ways[i] = 0
        else:
            ways[i] = ways[i - 1]
            if i > 1:
                ways[i] = ways[i] + ways[i - 2]
    return ways[-1]
