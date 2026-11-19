# Python/Gibbon research snapshot

This branch preserves both prototypes, not a finished Python implementation or a decision-tree performance result:

- `python-frontend/`: actual Python-source translation into Gibbon Haskell, including recursive datatypes, range-loop lowering, fixed-size int/float vectors, read-only vector parameters, and a hand-written illustrative decision-tree example.
- `python-kernels/`: earlier runtime schema-reflection / generated sum-and-add / ctypes bridge, plus native-construction and layout spikes. These fixed operation templates are distinct from the source frontend.

## Research status

The decision-tree frontend extension was built before the research order was clarified. It remains an experimental prototype. The agreed next investigation is to choose a production decision-tree implementation, hand-port inference into Gibbon Haskell, validate predictions and compare performance before deciding on further frontend work. That production-baseline experiment has **not** been completed. No Gibbon-versus-scikit-learn/Futhark speedup is claimed.

## Build artifacts and reproducibility

Compiler executables, runtime/shared libraries, generated C, caches, raw execution logs, agent prompts and workspace checkpoints are intentionally not committed. The checked-in handwritten C files are ABI adapters; their included generated C must be regenerated.

Existing native verification used the sequential shell in `python-kernels/shell-sequential.nix`, the compiler from `/home/noir/gibbon-python-mvp/python-kernels/spikes/native/gibbon`, and the runtime in that existing worktree. The executable's exact source build revision is not established. This branch preserves the source baseline of that worktree rather than rebasing the prototype onto newer compiler APIs.

A fresh clone must build Gibbon and its runtime first. The historical scripts expect the resulting compiler at `python-kernels/spikes/native/gibbon`; provide it there (a local symlink is sufficient). The branch does not automate a clean-clone compiler bootstrap. The old `python-kernels` bridge additionally assumes its observed private generated cursor-tuple ABI.

Source-only tests, from the repository root:

```sh
python3 -m unittest discover -s python-frontend -v
python3 -m unittest discover -s python-kernels/frontend -v
```

Native tests, after entering `nix-shell python-kernels/shell-sequential.nix` and providing the compiler/runtime:

```sh
cd python-frontend
python3 verify_native.py --gibbon ../python-kernels/spikes/native/gibbon --gibbon-root ..
python3 verify_bounds.py --gibbon ../python-kernels/spikes/native/gibbon --gibbon-root ..
python3 verify_decision_trees.py --gibbon ../python-kernels/spikes/native/gibbon --gibbon-root ..
```

The decision-tree verifier is separate from the older fixture registry. `examples/test.py` preserves the user's experiment; its post-loop `return i` is deliberately unsupported and is not part of the successful fixture suite. Gibbon Float is float32, not Python float64; numeric tests use a tolerance and do not establish general threshold equivalence near rounding boundaries. The BST fixture alone uses `--no-rcopies`.

The older bridge benchmark JSON files record historical exploratory measurements, not decision-tree benchmark results or fresh publication-time measurements.
