# Python source frontend spike

Translate actual Python function bodies to Gibbon Haskell, then use the existing compiler. This is not the older dataclass/fixed-sum-template bridge.

## Run

Edit locally in `/home/noir/projects/gibbon-decision-trees` on the Hermes host, then:

```sh
bash remote-test.sh
```

This rsyncs just this directory (no `--delete`; excludes `build/` and `__pycache__/`) and runs tests/compilation over SSH on `noir@vulcan.moe`. Native artifacts remain at `/home/noir/gibbon-python-mvp/python-frontend/build/`.

Translate without compiling:

```sh
python3 translate.py examples/vector.py -o vector.hs
python3 -m unittest discover -v
```

## Supported subset

- Annotated dataclass constructors, one recursive union per module, typed functions, helpers and recursion.
- Exhaustive positional constructor matching; scalar fields precede packed recursive fields.
- Integers/booleans and float32 values, homogeneous arithmetic/comparisons, fresh local bindings, terminal `if`/`else`. Float operators map to Gibbon's existing floating-point primitives; no implicit int/float conversion.
- `range(stop)`, `range(start, stop)`, and literal nonzero signed steps; lowered to generated top-level recursion with loop-carried bindings.
- Sequential assignment and `+=`, `-=`, `*=`; conditional updates inside loop bodies.
- Local fixed-size homogeneous integer or float lists initialized with `[seed] * count` or literals such as `[1, -2, helper(3)]` and `[1.0, -0.5]`; zero/negative repetition counts yield empty vectors. `[]` defaults to an integer vector; use `[0.0] * 0` for an empty float vector.
- Read-only `list[int]` and `list[float]` function parameters, including recursive forwarding and use alongside packed ADTs. Writes, rebinding, and direct aliases of borrowed parameters are rejected in every function, including unused functions.
- `len(values)`, integer indexing (including valid negative indices), and indexed writes to local vectors, lowered to Gibbon vector primitives.

Loop bounds are evaluated once. Captured state is threaded through helpers; assignment order is preserved. Loop targets must be fresh and cannot be referenced after the loop or assigned in its body. Loop-body locals cannot escape unless initialized before the loop. Nested loops, `break`, `continue`, early loop returns and `for`/`else` are not supported.

Lists are deliberately restricted: no aliases, resizing, slicing, mixed/nested list literals, list results, or lists in ADTs. Borrowed list parameters are read-only; only locally allocated vectors may be updated. They are not full Python lists. Invalid indices fail the native process with a message, not a Python exception. There is no user-controlled ADT mutation.

Also unsupported: arbitrary imports/calls, closures, keyword calls, nested patterns, match guards, chained comparisons and general nonterminal `if`/`match` fallthrough. The translator reads declarations; it does not execute the input. Docstrings are accepted. No CPython fallback.

Integer literals are range-checked, but arithmetic/loop increment overflow is not: comparisons with Python are only claimed where all intermediate integer values fit signed 64-bit integers. `float` maps to Gibbon's 32-bit `GibFloat` (`typedef float` in its runtime header), not Python float64. Finite float literals outside float32's maximum range are rejected; representable literals and arithmetic round to float32 and tiny literals may underflow. Threshold decisions near rounding boundaries can therefore differ from CPython. There is no implicit numeric promotion and no speedup or native FFI/ownership claim.

## Verification

Latest full run on Vulcan: **29 frontend test methods, 35 existing native comparisons, 17 additional decision-tree/float/vector native comparisons, and 7 bounds-failure checks passed** (4 existing + 3 float-feature checks). Float results are compared with a tolerance, not bitwise float64 equality. The BST example uses the explicitly recorded `--no-rcopies` workaround; decision trees and the other examples use the default tested packed configuration. See [sample programs](examples/README.md), [decision-tree milestone](DECISION_TREES.md) and [how transpilation works](HOW_IT_WORKS.md).

Examples include:
- `tree.py`: recursive construction, transformation and fold (224).
- `irregular.py`: custom conditional score and transformation (-10).
- `loop.py`: two sequentially dependent accumulators (51).
- `loop_reverse.py`: reverse step, conditional updates and sequential loops (42).
- `vector.py`: fill, sum and negative indexing (114).
- `vector_order.py`: reads before/after writes (644).
- `vector_prefix.py`: loop-carried vector updates read by later iterations (41).

The harness also tests empty/negative ranges, several list lengths, empty lists, range-bound snapshots, booleans and recursive-tree edge cases. Trusted fixtures are executed under CPython only as references; generated programs execute natively. Records are in `build/results.json` and `build/bounds/results.json`, alongside Haskell/C/executables and per-case logs.

## Research findings

These Python-native imperative idioms do not require direct L2 integration: range loops become recursion; unaliased indexed writes use existing `inplacevupdate`. This demonstrates a more natural surface, NOT strictly greater expressiveness than Gibbon Haskell.

A real target-language wrinkle surfaced: a let-bound `valloc` remained polymorphic through type checking and failed at `toL1`. Emitting a local declaration `let { vec :: Vector Int; vec = valloc count } in ...` resolves it. Expression annotations and typed let-patterns were rejected by this Haskell frontend. `probe_vectors.py` retains the minimal variants; remote `build/probes/verbose.log` shows the unresolved element type. No core compiler fix was necessary.

Next substantive frontier: nested control flow and explicit alias/effect semantics, or a realistic mixed tree/vector workload. Do not infer general Python mutation semantics from these restricted tests.

## Files and provenance

`translate.py` holds the AST validation/type checks and direct Haskell emitter (no separate typed IR yet). `test_*.py` cover translation/rejection; `verify_native.py` and `verify_bounds.py` exercise generated binaries. Runtime helpers implement list initialization/bounds checks, not application-specific algorithms.

Local branch `aniruddh/python-source-spike`, base `5f4b6973`; original local checkout untouched apart from ignored build artifacts. Remote checkout `/home/noir/gibbon-python-mvp`, source HEAD `af1d2f0c78ece292118f317c10bb9fda5e7a83d0`; reuses its existing `python-kernels/spikes/native/gibbon` executable and sequential Nix shell (exact executable build revision not established). Initial local compiler rebuild failed under GHC 9.6.7 (`foldl'` not in scope); abandoned without source fixes. All successful native verification ran on Vulcan. No core-source changes, commits or pushes.
