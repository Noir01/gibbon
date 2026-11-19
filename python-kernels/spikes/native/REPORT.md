# Native scalar bridge and transformation spike

## Verified prior checkpoint

The earlier scalar bridge is documented below. The generated-code-only sum adapter's Python nested negative fixture returned 9.

## Advisor-verified transformation checkpoint

After this pupil returned, advisor replaced its unused constant main with a runtime-size recursive witness that actually calls add_ints. A readPackedFile witness first exposed an InferRegionScope MMapR lookup error, so the runtime-size witness avoids that unrelated compiler path without core changes. Generated C now contains add_ints with input end, output end, output cursor, input cursor, and amount arguments; ordinary cases only read, write, and recurse under --biginf --no-rcopies. They write exactly the trusted flat input's size and do not allocate or grow regions.

Advisor extended expr_bridge.c to call that generated traversal into an independent caller-owned output buffer, checking capacity before entry. Shared library compiled with matching _GIBBON_GENGC=0, _GIBBON_SIMPLE_WRITE_BARRIER=0, _GIBBON_EAGER_PROMOTION=1. All three test_bridge tests now pass: native sum returned 9; adding 4 to three integer fields produced native sum 21; independent adding -2 produced sum 3; input bytes remained unchanged; insufficient capacity was rejected. These are actual ctypes executions, not interpreter or subprocess computations.

This confirms only valid, flat, shape-preserving Expr buffers on the current host; no arbitrary input validation, overflow safety, chunked regions, or GC ownership is claimed. Python caller owns input/output arrays. Generic schema-driven handles and two-schema integration are assigned separately.

## Historical transformation attempt (superseded)

Added `expr_sum_add.hs` with explicit `sum_ints :: Expr -> Int` and `add_ints :: Expr -> Int -> Expr`. Generated C with the working compiler from the required shell:

```
nix-shell python-kernels/shell-sequential.nix --run 'cd python-kernels/spikes/native && ./gibbon --hs --packed --biginf --no-rcopies --toC --cfile expr_sum_add.c expr_sum_add.hs'
```

This succeeds, but does NOT meet the dynamic-input requirement: generated `main` builds a constant tree. Inspection of generated `expr_sum_add.c` shows `sum_ints` is emitted, `add_ints` is absent (dead-code elimination), and copy/traverse helpers are present. `main` calls `gib_init`, info/symbol-table initialization, and allocates a big-infinite region for its constant tree. Therefore this output does not establish an allocation-free caller-buffer writer ABI. No ABI was guessed and no transformation result is claimed.

The attempted `.gib` source was rejected by `--hs` as invalid Haskell; the replacement `.hs` compiles, but the needed dynamic packed-file entrypoint is not yet supplied. The expanded ctypes tests are TDD-first and currently cannot pass: `expr_add` has not been implemented. They are not verified.

## Safety/ownership conclusion

No-init scalar `expr_sum` remains a narrow prior claim for its valid flat input fixture. It is not a claim about generated writer code or normal chunked runtime regions. Until a generated live `add_ints` traversal is inspected, we cannot establish whether it allocates, writes only cursors, invokes barriers, checks growth, or needs RTS ownership/init. Buffer slack alone is not justified.

## Original scalar checkpoint and reproduction

A real shared library existed as `libexpr_bridge.so`. `expr_bridge.c` includes generated `expr.c` (renaming main) and adapts `sum_ints(end, root).field2` to `int64_t expr_sum(data, length)`. Python's nested negative fixture returned 9.

From worktree root, enter `nix-shell python-kernels/shell-sequential.nix`, then:

```
gcc -fPIC -shared -O2 -D_GIBBON_GENGC=0 \
  -I gibbon-rts/rts-c -I deps/uthash \
  python-kernels/spikes/native/expr_bridge.c gibbon-rts/rts-c/gibbon_rts.c \
  -L gibbon-rts/build -lgibbon_rts_ng -lm \
  -Wl,-rpath,"$GIBBONDIR/gibbon-rts/build" \
  -o python-kernels/spikes/native/libexpr_bridge.so
python3 -m unittest discover -s python-kernels/spikes/native -p test_bridge.py -v
```

The new tests also require `expr_add`; they are not compatible with the prior-only shared object and are not passing. Runtime compile flag matching for a transformed library was not validated.

## Limits

Trusted valid flat buffers only; native-endian/native-width host encoding; no indirections, malformed/untrusted input, or arithmetic overflow. No general ownership proof. No transformation proof yet.
