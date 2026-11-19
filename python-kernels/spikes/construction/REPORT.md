# Packed-tree construction spike report

Status: complete; confined to `python-kernels/spikes/construction/`.

The first test run was RED: shallow native sum and byte equality passed, while the Python codec equality failed because it initially returned distinct dataclass types (`Leaf(value=1) != Leaf(value=1)`). The codec was changed to use the existing `integration/readme_tree.py` constructors. A subsequent import failure exposed a `construction.so` / `construction.py` name collision; the library is now `tree_construction_native.so`, and the stale conflicting artifact was removed. GREEN: 5 tests pass.

Generated ABI observed in `module.c`:

`GibCursorGibCursorGibCursorProd mk_tree(GibCursor end_r_308, GibCursor loc_307, GibInt depth_10_84_143)`

The returned tuple's `field0` is the returned end cursor, `field1` the root start cursor, and `field2` the cursor immediately after the written tree. The wrapper uses `field2 - start` as byte count. Generated `sum_leaves` returns `GibCursorGibCursorGibIntProd`; its `field2` is the integer sum.

Under `--biginf`, the ordinary `mk_tree` generated constructor path writes tags and integer payloads directly through `loc_307`, recursively invoking `mk_tree` with the destination cursor. Its inspected function body has no runtime allocation, growth, promotion, or region-allocation calls. This establishes caller-buffer construction only for this generated function/path and build configuration; it is not a zero-allocation claim for Python or runtime initialization generally.

Packed schema bytes are one tag byte followed by native 8-byte integer fields; Leaf is 9 bytes, Node is a 9-byte header followed by two trees. Exact size recurrence: `S(0)=9`, `S(d)=9+2*S(d-1)`, hence `S(d)=18*2^d-9`. Maximum depth 12 uses 73,719 bytes. API validates exact int depths 0..12; negative, bool, and non-int input is rejected. Native helper rejects inadequate capacity before calling the generated writer. Caller owns the ctypes bytes; each output handle keeps both storage and its `ConstructionOps`/library reference. No Python tree is constructed, traversed, or packed by `build_tree`; it computes size, allocates storage, and calls native code.

Validation includes exact raw byte comparisons against existing `Ops.pack(mk_tree(depth))` for depths 0, 1, 2, and 5; `to_python` equality at 0 and 1; native depth-10 leaf sum against the Python reference (1024); repeated independent storage; depth/type validation; and native insufficient-capacity rejection. The output itself is consumed by the generated native sum kernel.

Build and test command (from checkout root):

`nix-shell python-kernels/shell-sequential.nix --run 'set -e; export PYTHONPATH=/home/noir/gibbon-python-mvp/python-kernels/frontend:/home/noir/gibbon-python-mvp/python-kernels/integration:/home/noir/gibbon-python-mvp/python-kernels/spikes/construction; cd /home/noir/gibbon-python-mvp/python-kernels/spikes/construction; python3 -m unittest -v test_construction'`

The test run invokes Gibbon with `--hs --packed --biginf --no-rcopies --toC module.hs`, then GCC with `-fPIC -shared -Wl,-Bsymbolic`, `_GIBBON_GENGC=0`, `_GIBBON_SIMPLE_WRITE_BARRIER=0`, `_GIBBON_EAGER_PROMOTION=1`, RTS/uthash include paths, and the RTS library rpath as in the established build.

Demo: from the same shell/environment, run `python3 demo.py` in this directory. Generated C/shared library are retained in this spike directory for inspection. No frontend/native/core source, model config, or git history was changed.

## Advisor verification

Independently reran all five tests and the demo successfully. Inspected generated mk_tree body at module.c lines 143–188: it writes tags/integers directly and passes the returned write cursor from the first child into the second. No allocator or growth call appears in that body.

Added and ran benchmark.py: eleven samples per path at depths 5, 10, 12, excluding compilation, including native buffer allocation and Python construction+packing respectively. Each result is byte-checked outside timing. At each depth, additionally passed native-produced storage directly to the separately compiled existing leaf-sum library's private ABI; correct sums, including 4096 at depth 12. This private ABI check does NOT make the new TreeHandle accepted by public Ops methods.

Exploratory medians (milliseconds): depth5 native0.049711 versus Python+pack0.613317; depth10 native0.037045 versus6.373322; depth12 native0.062091 versus28.902089. Raw samples: benchmark-results.json. These are noisy one-machine measurements of a simple balanced builder, not a general speedup or application benchmark. Native small-call timings are especially sensitive to scheduling/cache effects. Python packing includes its current validation/statistics overhead. Compilation, materialization, and downstream operations are excluded from these construction-only timings.

Remaining limits: handwritten single schema/builder; exact buffer size known from depth; build recompiles and writes fixed artifact filenames; depth capped at12; flat host-specific layout/runtime flags; optional Python codec assumes little-endian; no integration with compile_type/Packed metadata or chunked region lifetime. Existing public add_ints cannot directly accept the spike's handle.
