# Sample programs

Each file defines `main()` and is both ordinary Python and frontend input. There are no `@kernel` decorators or bridge calls. `python3 example.py` only defines functions; the verification harness invokes `main()` and compares with the compiled executable.

New examples (all executed natively on Vulcan):

- `decision_tree.py` → **2.5**. Recursive packed decision tree with floating-point thresholds and a read-only external `list[float]` feature vector. `verify_decision_trees.py` separately checks branch choices, equality, repeated use, float arithmetic and feature bounds; it runs from `remote-test.sh`. This is a hand-written test model, not training or model import; Gibbon uses float32, not Python float64.

- `vector_postfix.py` → **19**. Evaluates `(3 + 4) * 2 + 5` using a vector-backed stack. Tokens use `-1` for addition and `-2` for multiplication; assumes a well-formed expression. Demonstrates data-dependent reads/writes, a changing stack pointer, and nested conditionals.
- `vector_paths.py` → **6**. Dynamic programming: count paths to step 7 with 1- or 2-step moves, without landing on blocked step 3. Each vector entry depends on earlier computed entries.
- `vector_literal.py` → **34**. Literal initialization with function calls and arithmetic, mutation, negative indexing, and a fold.
- `accumulate.py` → **45**. Working companion to the remote `test.py`: returns the accumulator rather than a loop variable after the loop. The original user file is preserved; post-loop use of the loop target remains unsupported.

- `fibonacci.py` → **6765**. Iterative Fibonacci with a temporary and two changing accumulator variables.
- `polynomial.py` → **42**. Horner evaluation of `2 + 3*x - 4*x*x + x*x*x` at `x=5`, using vector coefficients and a reverse range.
- `histogram.py` → **354**. Category frequencies `[4,5,3]`, encoded as `4 + 10*5 + 100*3`; exercises reads used as write indices and nested conditionals.
- `expression.py` → **63**. A four-constructor arithmetic/conditional expression interpreter.
- `bst.py` → **45**. Persistent BST insertion through a loop, then re-insertion of a duplicate and a sum. **Requires `--no-rcopies`** with the tested compiler; the harness applies and records that flag. Default compilation fails in L2 type checking; `--no-ran` also fails later. Original failure logs remain under remote `build/bst*.log`.

Older starting points: `tree.py`, `irregular.py`, `loop.py`, `loop_reverse.py`, `vector.py`, `vector_order.py`, `vector_prefix.py`, `scalar.py`, `predicate.py`.

## Try them

From the local `python-frontend` directory:

```sh
# Sync and compile/run all examples remotely, checking CPython references.
bash remote-test.sh

# Inspect generated Gibbon locally without native compilation.
python3 translate.py examples/fibonacci.py -o /home/aniruddh/.hermes/cache/scratch/fibonacci.hs

# Run just the Python reference locally.
python3 -c 'import runpy; print(runpy.run_path("examples/fibonacci.py")["main"]())'
```

Remote generated source is `/home/noir/gibbon-python-mvp/python-frontend/build/<example>.hs`; executables are alongside it. The runner uses packed compilation and GCC, with no timing/performance claims.
