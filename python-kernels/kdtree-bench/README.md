# k-d tree nearest-neighbour benchmark

Exact 1-nearest-neighbour search over uniform float32 points: a hand-written
Gibbon k-d tree (`KDTree.hs.in`, packed and pointer backends) against
scikit-learn's `KDTree` and a plain C k-d tree (`baseline.c`).

    python3 bench.py            # d = 2, 3, 8, 16; 100k points, 10k queries
    python3 bench.py --quick    # d = 2, 8; 20k points, 2k queries
    python3 bench.py --dims 16 --queries 1000 --out results-d16.json

Needs GHC/cabal for the Gibbon compiler, gcc, NumPy and scikit-learn.
Results go to `results/results.json` (or `results-quick.json`) with the
machine, library versions and Gibbon commit.

## What is measured

- **Build**: constructing the tree from the already-loaded point array.
- **Query**: one batch of all queries, run `QUERY_ITERS` times and reported
  per query. Gibbon times the batch with `iterate`, C with a loop, and
  scikit-learn times `tree.query(Q, k=1)` (one call for the whole batch).
- Gibbon and C run `REPEATS` fresh processes; scikit-learn builds `REPEATS`
  trees in-process. Medians are reported.

Gibbon and C build the same tree: the split axis cycles with depth, and each
node sorts its points by `(coordinate, index)` and takes the median point, so
build is O(n log² n). scikit-learn uses a different build (quickselect,
widest-spread axis, leaf buckets) and is timed at leaf sizes 40 (its default)
and 1. Every engine's answers are checked against scikit-learn:
both the index and the distance (an engine may differ on a tie but never be
farther).

Input files must have exactly as many lines as `--array-input-length`, because
`readArrayFile` on this branch writes past its vector otherwise
([#2](https://github.com/Noir01/gibbon/pull/2)).
