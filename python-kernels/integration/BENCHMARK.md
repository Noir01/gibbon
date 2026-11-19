# Integration benchmark: advisor rerun

Reproduce from the worktree root:

```sh
nix-shell python-kernels/shell-sequential.nix --run 'set -e; export PYTHONPATH=python-kernels/frontend; python3 python-kernels/integration/benchmark.py'
```

Raw samples: `benchmark-results.json`. Advisor independently reran the benchmark after adding pure-Python single-operation baselines, end-to-end pack + three transforms + sum, and skewed fixtures. Five fixtures passed correctness checks. One compiled schema/library is reused across fixture sizes and shapes. Each operation uses seven timed repetitions after one warmup; uncached compilation uses five repetitions after one warmup. Compilation is measured once independently of value shape; its median was 1.538 seconds. This is uncached application compilation, not a cold OS/compiler cache.

Host: Linux 6.18.28 x86_64, Python 3.13.12, Intel Xeon E5-2667 v3 @ 3.20GHz (CPU model read from /proc/cpuinfo). No CPU affinity or isolated-machine control was applied. Several measurements vary substantially; these are exploratory measurements, not stable performance guarantees.

## Median observations (milliseconds)

- Balanced, 63 nodes: packing 0.4267; retained native sequence 0.0448; equivalent Python sequence 0.1294; packing + native sequence 0.4826.
- Balanced, 1,023 nodes: packing 6.6487; retained native sequence 0.0987; Python sequence 2.4165; packing + native sequence 2.5577.
- Balanced, 8,191 nodes: packing 21.3514; retained native sequence 0.2015; Python sequence 9.0214; packing + native sequence 20.8983; unpacking 6.9641.
- Skewed, 65 nodes: packing 0.1527; retained native sequence 0.0180; Python sequence 0.0491; packing + native sequence 0.1757.
- Skewed, 193 nodes: packing 0.5220; retained native sequence 0.0238; Python sequence 0.1468; packing + native sequence 0.5538.

A sequence means three shape-preserving increments followed by a scalar sum. Native transforms stay packed; no Python object reconstruction occurs between them. Native timings include Python method/ctypes overhead and output buffer allocation. End-to-end sequence includes initial packing but not compilation or final unpacking because its result is a scalar.

## Interpretation

For the largest balanced fixture, the already-packed native sequence was about 44.76 times faster in this run, but including initial packing made the sequence about 2.32 times slower than Python. A final tree materialization would incur additional unpacking cost. This supports retained buffers as an important API feature, not an end-to-end speedup claim.

The separately measured packing time can exceed the pack+sequence median due to noise/order/cache/GC differences; do not add independent medians as if they describe one measured run. Conversion is the current dominant cost. Packing is a validating pure-Python implementation, not optimized. Further work should improve the codec and measure longer retained workloads under controlled conditions before making broader claims.

Correctness checks run outside timed intervals. Fixtures use fresh objects and counts/byte sizes are computed by the runner. Native paths are the present host-specific flat-buffer specialization, not general chunked RTS/GC behavior.
