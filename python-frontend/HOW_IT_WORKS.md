# How the transpilation works

## The pipeline

1. **Parse, without execution.** `ast.parse()` reads the source. A function, assignment, match, call or loop becomes an AST node. Dataclass declarations are inspected syntactically; the translator does not import the file or call its functions.
2. **Collect declarations.** Record constructor fields, the recursive union, and function signatures before translating bodies, so recursion and calls to later helpers can resolve.
3. **Validate and type-check.** Whitelist accepted constructs; resolve variables and calls; check argument/return types, constructor arities and match coverage. Unsupported features get Python source locations. This is a static subset, not a CPython fallback system.
4. **Desugar and emit Haskell.** This prototype uses small recursive emitters whose expressions return `(generated_text, type)`. It does not yet build a separate typed IR. ADTs become `data` declarations, matches become `case`, calls become Haskell applications, and arithmetic becomes typed primitive expressions.
5. **Compile remotely.** Local edits are rsynced to Vulcan. The existing Gibbon compiler reads the generated Haskell, performs its own type checking/representation passes, emits C, and invokes GCC to produce a packed-data executable.
6. **Verify independently.** Only the test harness executes trusted Python fixtures to obtain reference results. It runs each native executable separately and records comparisons. It does not use CPython to implement the compiled algorithms.

## Why assignments and loops are not text substitution

Python's `x = x + 1` needs a new binding. A naive Haskell `let x = x + 1` is recursive and wrong. The translator uses fresh names: `let x_new = x_old + 1 in ...`. The `p_` prefix and fresh suffixes also avoid Haskell reserved names and accidental capture.

A range loop becomes a generated top-level recursive helper with parameters for the index, stop bound and incoming state. The body computes updated bindings in order, then tail-calls the helper. At termination the helper evaluates the post-loop continuation using the final state. Bounds are captured once, even when a source variable used in a bound changes during the loop.

Fibonacci's two accumulators are a useful check: updating `previous` must not change the saved old value needed by `current`. Empty/reverse loops and sequential loops are independently exercised.

## Vectors and mutation

Restricted `[seed] * count` initialization emits allocation and an initialization helper. `len`, indexing and writes become `vlength`, `vnth` and `inplacevupdate`. Generated bindings thread updated vector handles through subsequent operations. Negative indices are normalized; invalid indices terminate with a diagnostic. Aliasing/resizing is rejected rather than silently implementing Python's full list semantics.

An allocation bound with an inferred `let` type remained polymorphic in Gibbon and failed at `toL1`. A supported local declaration fixes it:

```haskell
let { vec :: Vector Int; vec = valloc count } in ...
```

The tested frontend rejected expression annotations and typed let-patterns for this purpose. The verbose backend dump and `probe_vectors.py` retain the evidence.

## A second real compiler boundary

Persistent BST insertion produces valid translated source, but default packed compilation hits an L2 `StartOfPkdCursor` type-check failure. `--no-rcopies` compiles and runs it correctly in the tested case. This retains copy calls instead of converting them to indirections; it is a backend configuration workaround, not a Python-source rewrite or a fix to the compiler. The harness records it explicitly for the BST example. Do not claim default compilation succeeds for every sample.

## What this establishes

Familiar imperative Python syntax can target Gibbon's existing Haskell frontend. It does not establish support for all Python semantics, better performance, or strictly more expressiveness than that frontend. Integer overflow, general mutation/aliasing, full control flow and native Python FFI remain separate problems.
