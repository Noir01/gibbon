# Decision-tree inference milestone

Scope: compile user-written recursive prediction over a packed ADT and an external read-only floating-point feature vector, using the existing Gibbon Haskell route. No training, model import, tensors, nested vectors, vector fields/results, aliasing, performance claims, commits or compiler/runtime modifications.

Frontend contract:
- `float` scalar annotations, literals, unary minus, homogeneous + - * arithmetic and comparisons; target Gibbon Float (establish runtime precision during native verification), no implicit int/float promotion, reject nonfinite/out-of-target-range literals.
- Local homogeneous list[int] and list[float] literal/repetition operations with correct element types; [] remains integer vector unless context support is explicitly implemented.
- User function parameters list[int]/list[float] allowed, conservatively read-only. Forbid writes/rebinding of borrowed vector parameters, direct vector aliases, vector returns and vector fields. Passing borrowed vectors recursively or to another read-only helper is allowed. All vector parameters in all functions obey same rule, preventing indirect mutation.
- Preserve existing int behavior, bounds checks and rejection tests except intentional float-literal support changes. Bare main() may return Int, Bool or Float.
- Scalar-only function returns; generic compiler logic, no decision-tree pattern recognition.

Workspaces: authoritative edits here (/home/noir/projects/gibbon-decision-trees), rsync task files without deletion to vulcan:/home/noir/gibbon-python-mvp/python-frontend/. Use SSH alias `vulcan` to select configured key. Heavy compilation exclusively on Vulcan. No AI runtimes on Vulcan.

Ownership: implementation pupil owns translate.py and test_decision_frontend.py only. Parent owns fixtures, native verifier, sync script, documentation and integration. Preserve remote user examples/test.py and all existing artifacts. Snapshot hashes before sync and inspect changed files.

Acceptance: frontend tests; native decision-tree comparisons against CPython spanning both root branches, second-level branches, threshold equality, negative feature index behavior/bounds, leaf-only model, and reuse with multiple feature vectors. Run existing complete regression + bounds checks. Record actual flags and observed Float precision; no speedup claim.
