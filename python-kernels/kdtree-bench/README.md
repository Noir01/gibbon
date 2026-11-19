# k-d tree nearest-neighbour benchmark

Exact 1-nearest-neighbour search over uniform float32 points in d = 2, 3, 4,
8, 16 dimensions and n = 10^4, 10^5, 10^6 points. A hand-written Gibbon k-d
tree (`KDTree.hs.in`, packed and pointer backends) against:

- **scikit-learn** `KDTree`, leaf size 40 (its default) and 1: the primary
  comparison.
- **SciPy** `cKDTree` (default leaf size 16).
- **nanoflann** v1.8.0 (`nanoflann_bench.cpp`), leaf size 10 (its default)
  and 1: the well-known C/C++ library.
- **C** (`baseline.c`): a plain C tree built and searched exactly like the
  Gibbon one.
- **brute force** (`brute.c`): a linear scan, to show where a tree stops
  paying off.

```
python3 bench.py --gibbon PATH/TO/gibbon --nanoflann PATH/TO/nanoflann   # full run
python3 bench.py --quick --gibbon ... --nanoflann ...                    # d = 2, 8; 20k points
python3 bench.py --dims 16 --points 1000000 --max-queries 1000 --out results-d16.json
python3 bench.py --no-gibbon ...                                         # libraries only
python3 summarize.py results/results.json > results/SUMMARY.md
python3 counters.py --dims 2 8 16 --points 100000 --gibbon ...          # perf counters
```

`--nanoflann` is a checkout of https://github.com/jlblancoc/nanoflann (only
its header is used). Needs GHC/cabal for the Gibbon compiler, gcc/g++,
NumPy, SciPy and scikit-learn; `counters.py` also needs `perf`. Results go to
`results/results.json` with the machine, library versions and Gibbon commit.
Pin the run to one core (`taskset -c N`, `OMP_NUM_THREADS=1`): every engine
is single-threaded.

## What is measured

- **Build**: constructing the tree from the already-loaded point array.
- **Query**: one batch of all queries, run `QUERY_ITERS` (5) times and
  reported per query. Gibbon times the batch with `iterate`, C/C++ with a
  loop, and the Python libraries time one `tree.query(Q, k=1)` call for the
  whole batch.
- Gibbon, C and nanoflann run `REPEATS` (5) fresh processes; the Python
  libraries build `REPEATS` trees in-process. Medians are reported.
- **Queries per dataset** are chosen so one scikit-learn (leaf 40) batch
  takes about a second, between 200 and 10,000; every tree engine gets the
  same queries. Brute force gets only as many of those queries as fit in
  about a second, and 3 runs x up to 3 batches; both counts are in the
  results.
- **Python call overhead** (`call_overhead` in the scikit-learn record):
  the time of one `tree.query` call on a single point against the same
  point's share of a batch call.

Gibbon and C build the same tree: the split axis cycles with depth, and each
node sorts its points by `(coordinate, index)` and takes the median point, so
build is O(n log² n) and every node holds one point. The libraries use
bucketed leaves and quickselect builds, and choose split axes by spread.
scikit-learn computes in float64 (the float32 points are converted); the
others use float32.

Every engine's answers are checked against scikit-learn: an engine may
return a different index on a tie (counted as `index_mismatches_vs_sklearn`)
but is never farther than scikit-learn's neighbour by more than 1e-6
relative. The Gibbon answers must match the C tree's exactly.

`counters.py` runs each native engine under `perf stat` with 1 and 21 query
batches (median of 3 runs each) and divides the difference by the extra
queries, which cancels input parsing and build. The C tree also counts the nodes its queries visit
(outside the timed loop); the Gibbon trees visit the same nodes. scikit-learn
is sampled with `perf record` during its query batches only.

Input files must have exactly as many lines as `--array-input-length`, because
`readArrayFile` on this branch writes past its vector otherwise
([#2](https://github.com/Noir01/gibbon/pull/2)).

## Results on triton

AMD Threadripper PRO 7965WX, one pinned core. Full tables are in
`results/SUMMARY.md`, raw samples in `results/results.json` and
`results/counters.json`. Every engine returned scikit-learn's distance on
every query (0 index mismatches, 0 farther answers), and both Gibbon backends
matched C exactly.

| d | packed vs sklearn leaf 40 | packed vs C | packed vs nanoflann leaf 10 |
|---|---|---|---|
| 2 | 2.7-2.8x faster | 1.05-1.12x slower | 1.2-1.4x slower |
| 3 | 2.3-2.7x faster | 1.13-1.24x slower | 1.5-1.6x slower |
| 4 | 1.7-2.6x faster | 1.32-1.54x slower | 1.9-2.1x slower |
| 8 | 1.15-1.5x slower | 1.6-1.7x slower | 4.7-4.9x slower |
| 16 | 1.9x (10^4) to 11x (10^6) slower | 1.6-2.0x slower | 4.2x (10^4) to 33x (10^6) slower |

Ranges are over n = 10^4, 10^5, 10^6.

**d = 16: the one-point-per-node trees are slower than brute force.** With
the split axis cycling over 16 axes, a tree of 10^6 points (20 levels) splits
each axis about once, so the pruning test rarely fires: the C tree visits 98%
of its nodes per query at 10^4 points, 93% at 10^5 and 67% at 10^6. A linear
scan beats C, packed and pointer at every n, and beats scikit-learn leaf 40 at
every n (3.8 ms against 4.5 ms per query at 10^6; SciPy and scikit-learn
leaf 1 tie with it there). Only nanoflann beats the scan at d16, and only from
10^5 points. This is the algorithm in `KDTree.hs.in` (cycling axis,
single-point nodes), not Gibbon's code generation: the C tree has the same
problem.

**Why packed falls behind C as d grows** (`counters.py`, n = 10^5). Packed
visits the same nodes as C and takes about as many cache misses (1.3x C's at
d4, 1.16x at d8, 1.02x at d16), but executes more instructions per node, and
the gap grows with d:

| d | C insn/node | packed insn/node | C cycles/node | packed cycles/node |
|---|---|---|---|---|
| 2 | 87 | 123 | 59 | 64 |
| 4 | 94 | 146 | 59 | 77 |
| 8 | 112 | 189 | 54 | 92 |
| 16 | 149 | 267 | 58 | 105 |

That is about 4.5 extra instructions per coordinate for C and 10.2 for
packed. In the generated C, `sqdist` reads each coordinate through
`gib_vector_nth`, which computes `data + elt_size * (lower + i)` for both
vectors; after inlining, each coordinate costs two `imul`s and reloads of the
vector headers, where `baseline.c` walks a `float *`. The pointer backend
executes fewer instructions than packed but takes 2-2.6x its cache misses,
which is why it falls furthest behind at 10^6 points. This attribution comes
from the counters and from reading the d=3 disassembly; a codegen change that
hoists the vector base was not tried.

**scikit-learn's Python overhead.** A `tree.query` call on one point costs
16-24 µs more than that point's share of a batch call (0.6 µs at d2, 10^4
points; 76 µs at d16, 10^6, where per-query variation dominates), so a
per-point loop would be dominated by call overhead, but a batch call pays it
once. In batch queries `perf record` puts at most 0.3% of samples in the
interpreter at every d; 60-68% are in the `_kd_tree` extension, 30-36% in
libm's `pow` (its default Minkowski p = 2 metric) and 1-3% in its heap. Its
low-d gap to C and Gibbon is float64 arithmetic and `pow`, not Python.

**Fewer queries or runs than the rest:**
- Tree engines at d16 got 9,733 queries at 10^4 points, 1,731 at 10^5 and
  222 at 10^6 (sized to a 1 s scikit-learn batch); every other case got
  10,000.
- Brute force got fewer queries from 10^5 points up (8,333 at d2 down to 104
  at d16, 10^6; listed in the summary table) and 3 runs of up to 3 batches
  instead of 5 x 5.
- `counters.py` ran only at n = 10^5, d = 2, 4, 8, 16, with 10,000 queries
  (500 at d16) and 3 `perf stat` runs per batch count.

**Not established:** counters at 10^4 and 10^6 points or at d3; per-node
costs for the libraries (their node counts are not recorded); whether hoisting
the vector base in Gibbon's codegen closes the instruction gap; data other
than uniform points, k > 1, or more than one core; FLANN and ANN.
