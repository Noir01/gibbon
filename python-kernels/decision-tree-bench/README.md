# Decision-tree inference in Gibbon: benchmark and findings

Question: is Gibbon's packed tree representation plus `Vector Float` features a
useful foundation for real decision-tree inference?

Short answer: **narrow it.** Gibbon runs real scikit-learn trees correctly and
builds packed trees quickly, but the packed layout is slower than Gibbon's own
pointer backend and a 30-line C array-of-structs loop at every size we tried.
The slowdown comes from fixable code generation, not from packing itself. It
is worth fixing those specific issues; it is not yet worth more frontend work on
decision trees.

## What is here

| File | Purpose |
| --- | --- |
| `bench.py` | Trains `DecisionTreeClassifier` models, exports them, compiles and runs every engine, verifies predictions, writes `results/results.json`. |
| `DecisionTree.hs.in` | Hand-written Gibbon inference (`data Tree = Leaf Int \| Split Int Float Tree Tree`, recursive `predict` over a `Vector Float`). Independent of the Python frontend. |
| `baseline.c` | C array-of-structs baseline (16-byte nodes, iterative loop, `-O3`). |
| `results/results.json` | Full run used below. |

Run (needs the Gibbon compiler built with GHC 9.10, `gcc`, scikit-learn, NumPy):

```
python3 bench.py           # 5 models x 4 batch sizes, ~5 min
python3 bench.py --quick   # 2 models x 3 batch sizes, ~1 min
```

Setup: 32 features, 4 classes, `make_classification` with seed 0; 200k training
rows, 100k held-out rows; `max_depth` in {4, 8, 12, 16, unlimited}. Engines:
scikit-learn `predict` (from Python), C AoS, Gibbon `--packed`, Gibbon
`--pointer`, all compiled with gcc 11.4 `-O3` on an 8-vCPU Xeon VM.

Timing: each engine is one process per (model, batch size). Gibbon reads the
model and inputs, builds the tree once, then `iterate`/`timeit` times only
`predictAll` over the batch; we report the median per-iteration time. Training,
export, compilation, file parsing and tree construction are reported separately
and never inside inference timings.

## Correctness and precision

Every engine matched `clf.predict` on all rows for all five models: 100k
held-out rows plus 45 to 75,888 threshold-boundary probes per model.

scikit-learn casts inputs to float32 but stores thresholds as float64 and tests
`x <= t`. Gibbon's `Float` is C `float` (32-bit). More than half of split
thresholds (13,966 of 25,296 in the unlimited-depth tree) are not representable
in float32.

- **Rounding to nearest float32 is wrong** on boundary inputs: 1 to 9 probe
  mismatches per model (0 on random held-out rows).
- **Rounding down to the largest float32 <= t is exact**: for float32 `x`,
  `x <= t64` iff `x <= round_down(t64)`. 0 mismatches everywhere. The exporter
  uses this.

So 32-bit `Float` is sufficient for sklearn trees, but only with a directed
rounding step in the exporter. A naive `float(t)` would be silently wrong.

## Performance (ns per row, median)

| Model (nodes) | Batch | sklearn | C AoS | Gibbon packed | Gibbon pointer |
| --- | ---: | ---: | ---: | ---: | ---: |
| depth 4 (31) | 1 | 108,427 | 29 | 31 | 29 |
| | 10k | 66 | 20 | 33 | 27 |
| | 100k | 81 | 23 | 48 | 29 |
| depth 8 (511) | 1 | 108,453 | 36 | 39 | 40 |
| | 10k | 98 | 48 | 63 | 50 |
| | 100k | 178 | 55 | 73 | 134 |
| depth 12 (6,143) | 1 | 108,129 | 45 | 52 | 46 |
| | 10k | 133 | 78 | 96 | 79 |
| | 100k | 217 | 89 | 206 | 187 |
| depth 16 (24,999) | 1 | 107,989 | 54 | 55 | 53 |
| | 10k | 175 | 108 | 133 | 118 |
| | 100k | 180 | 113 | 147 | 122 |
| unlimited (50,593, depth 51) | 1 | 108,262 | 102 | 219 | 97 |
| | 10k | 223 | 146 | 206 | 196 |
| | 100k | 661 | 215 | 335 | 210 |

Batch-100 numbers are in `results.json`; they are flattering for every compiled
engine because 100 rows repeated thousands of times train the branch predictor.

Reading the table:

- **Single query:** compiled engines take 30 to 100 ns and include clock
  overhead (about 20 ns). scikit-learn spends about 108 us in Python and
  validation per call, so single-query latency against sklearn is a comparison
  with its call overhead, not with tree traversal.
- **Batched throughput:** Gibbon packed is 1.2x to 2.3x slower than C AoS and
  usually slower than Gibbon pointer. It still beats sklearn's batched
  `predict` (which also computes class probabilities) by 1.05x to 2x.
- The VM is noisy: a few 100k cells (depth 8 pointer, depth 12 packed and
  pointer) are outliers. Rerun before quoting single cells.

Setup costs (unlimited-depth model): training 12.8 s, export 0.25 s, Gibbon
compile 0.5 to 0.8 s per backend, tree construction from the node array
**1.0 ms packed vs 2.6 ms pointer**. Packed construction is 2x to 4.5x faster
than pointer at every size: this is where packing clearly helps.

## Why packed is slower here

Inspecting the generated C (`work/<model>/tree_packed.c`):

1. **`predict` is not a loop.** Packed functions return `(end cursor, value)`
   structs, so each recursive call returns through every level. GCC turns
   pointer-mode `predict` into a loop (0 recursive calls in the binary) but keeps
   4 to 6 real calls in packed `predict`. Deep trees pay this most: 219 vs 97 ns for a
   single query on the depth-51 tree.
2. **Going right needs a random-access offset.** Every `Split` stores an 8-byte
   tagged offset to its right child (21 bytes per split, 9 per leaf, vs 16 in C
   AoS). Inference never walks the left subtree to reach the right one, so the
   preorder layout buys no locality beyond what a node array already has.
3. `Int` is 64-bit, so feature indices and leaf classes take 8 bytes each.

Traversal is a root-to-leaf path that skips half of every subtree, the opposite
of the whole-tree passes packed layouts are designed for.

## Limitations found

- **`readArrayFile` overflows the heap.** The generated reader loops over every
  line of the file and writes into a vector sized by `--array-input-length`
  with no bound check. A file with more lines than the given length segfaults
  intermittently (seen in both backends). The benchmark writes one input file per
  batch size to avoid it. This should be fixed in the RTS/codegen.
- **No flat vector I/O.** Features arrive as one float per line and are
  parsed with `sscanf`. Fine for a benchmark, not for real inputs.
- **Model must come from a file at run time** as a `Vector` of 5-tuples, then
  be rebuilt with a recursive `build`. There is no way to embed a model as a
  packed literal or read a packed tree directly from sklearn data.
- **Runtime build defaults to `clang`.** On machines without it, `--cc=gcc` is
  required.
- **Only `<=` on `Float` thresholds.** Categorical splits, missing-value routing
  and float64 thresholds are not expressible without changing the model type.

## Recommendation

Narrow: do not invest in more decision-tree frontend work now. If we continue,
the next steps in order are:

1. Make packed `predict` tail-recursive (do not return an end cursor from
   functions whose caller never uses it).
   Re-run this benchmark; packed should then match pointer.
2. Fix the `readArrayFile` bound check.
3. Only if packed then beats the C AoS loop, try alternative layouts
   (breadth-first or van Emde Boas order, 32-bit fields) and a batched Futhark
   comparison. Until then a Futhark comparison would measure codegen gaps, not
   layouts.
