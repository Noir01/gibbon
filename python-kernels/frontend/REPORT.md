Frontend bounded correctness pass

Scope: frontend.py, test_frontend.py, generate_examples.py, and generated examples only. No core edits, native bridge, codecs, or build cache.

Changes
- SchemaField, Constructor, and Schema are frozen stdlib dataclasses; nested fields/constructors are tuples.
- Annotation resolution uses typing.get_type_hints with explicit global/local namespaces and builtins. Recursive references match the actual root union object, not a class name. Unresolved names report a TypeError diagnostic.
- Haskell constructor/root names are validated, duplicate constructors rejected; generated functions have explicit signatures.
- Examples generate as .hs with standalone gibbon_main fixtures; generated library fragment has no main. Removed obsolete .gib examples.
- Root alias can be passed explicitly with extract_schema(..., root_name=...). No frame introspection.

RED/GREEN evidence
- Baseline: `python3 -m unittest -v test_frontend` passed the advisor's original 4 tests.
- Added mutation, postponed-annotation, same-named-foreign-type, constructor-validation, signature, determinism, nullary/unary tests before implementation. RED command: `python3 -m unittest -v test_frontend`; it failed on frozen mutation, int resolution, constructor validation, and missing signatures (and errored resolving postponed int).
- After implementation, `python3 -m unittest -v test_frontend` passed all 9 tests (GREEN). This includes assertion of the explicit unresolved-reference diagnostic.
- Example generation command: `python3 generate_examples.py` exited 0 and generated expr.hs and weighted_tree.hs.

Verification commands (run from this directory)
`python3 -m unittest -v test_frontend`
`python3 generate_examples.py`

Limitations
- No native Haskell/Gibbon compiler verification is available; do not treat generated files as compiler-validated. Supported field types remain int and direct root-recursive references only. Type aliases that obscure the root object are not inferred; provide root_name for naming only (recursive annotation must resolve to the root union itself). Integer overflow/runtime semantics and broader Haskell type syntax are outside this prototype. Constructor identifiers follow a deliberately small Haskell-style regex validation.
