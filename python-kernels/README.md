# Python-defined specialized Gibbon kernels: runnable prototype

This restricted approach-B prototype extracts Python dataclass-union schemas, generates Gibbon ADTs plus integer sum/add traversals, compiles a schema-specific shared library, and exposes it through ctypes. The traversal is Gibbon-generated code; Python performs conversion, validation, and buffer ownership.

## Run

From `/home/noir/gibbon-python-mvp`:

```sh
nix-shell python-kernels/shell-sequential.nix
export PYTHONPATH=python-kernels/frontend
python3 python-kernels/integration/demo.py
python3 -m unittest discover -s python-kernels/integration -v
python3 -m unittest discover -s python-kernels/frontend -v
python3 -m unittest discover -s python-kernels/spikes/native -p test_bridge.py -v
```

The initial compiler binary and RTS library are present in this worktree. Fresh-clone bootstrap is not automated yet. The sequential shell avoids OpenCilk; no compiler source rollback was needed.

Observed demo:
```
Original native sum: 9
Updated native sum: 21
Unpacked: Add(left=Lit(value=-4), right=Add(left=Lit(value=24), right=Lit(value=1)))
Original unchanged: True
```

## API

```python
ops = compile_type(Expr, globals(), name='Expr')
packed = ops.pack(python_tree)
result = ops.sum_ints(packed)
updated = ops.add_ints(packed, amount=4)
python_result = ops.unpack(updated)
```

Compilation is explicit at `compile_type`; each invocation currently produces a fresh build directory. By default `sum_ints` adds every integer field. To reproduce the README's leaf-only sum, select contributing constructors at compilation:

```python
ops = compile_type(Tree, globals(), name='Tree', sum_constructors=('Leaf',))
packed = ops.pack(mk_tree(10))
assert ops.sum_ints(packed) == 1024
```

Unselected constructors' integer fields are ignored by the sum, but their recursive children are still traversed. `add_ints` remains an all-integer-field transform; this sum option does not alter it. Run `integration/readme_bridge.py` with the same shell/PYTHONPATH setup for the verified native example. Arithmetic safety bounds remain conservative over all integer fields.

`add_ints` takes a runtime amount, returns an independent packed handle, and does not unpack or mutate its input. Handles retain their ops/library and Python-owned ctypes storage. Input deletion does not invalidate an output.

## Verified

Advisor independently executed:
- 7 integration tests with both Expr and WeightedTree native libraries alive simultaneously.
- 9 frontend tests.
- 3 low-level native bridge tests.
- 60 seeded random tree fixtures across both schemas compared with Python reference sums and transforms.
- Input preservation, output surviving input deletion, repeated transforms, wrong-schema rejection, invalid Python values, cycles/aliases/depth rejection, and overflow checks.

These are restricted prototype tests, not a proof that arbitrary ADTs or Gibbon runtime layouts work.

## Boundaries

- Flat host-native packed layout; integer fields and recursive root references only. No portable file-format promise, pointer tags, imported raw byte buffers, strings, lists, or general callbacks.
- Shape-preserving operations compiled with `--biginf --no-rcopies`; caller allocates output storage equal to input encoded length. This avoids chunked RTS region/GC ownership for the narrowly verified paths. It does not support arbitrary allocating kernels.
- Native kernels contain unaligned typed accesses; only this host/compiler combination is exercised.
- Recursion depth capped at 128; repeated dataclass identities are rejected, including acyclic sharing.
- Signed 64-bit fields and transform amounts. Sum rejects conservative intermediate-overflow bounds, possibly rejecting some cancellation-heavy trees whose final mathematical sum would fit.
- Explicit namespace/name for Python annotation resolution; standard positional dataclass construction supported by unpacking. User Python datatype definitions are trusted.
- Bridge is tied to the observed generated cursor-tuple ABI, checked during build. No stable public C ABI/versioning.
- Compilation caching, packaging/bootstrap, cleanup of build artifacts, memory stress/sanitizers, performance results, and broader layout support remain work.

Generated sources, build logs, bridge source and shared objects are retained under `integration/build/` for inspection. Use the Python interface, not the private low-level bridge on malformed data.
