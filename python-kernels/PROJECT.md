# Python-defined specialized Gibbon kernels

Advisor: GPT 6.1 Sol. Pupils: explicit gpt-6-luna via openai-codex, verified with a successful live CLI request. Parent keeps architecture decisions and validates pupil artifacts. No unrequested provider fallback to an expensive model.

Full plan: /home/noir/gibbon-python-mvp-plan.md
Worktree: /home/noir/gibbon-python-mvp
Branch: aniruddh/python-kernels-mvp
Original checkout and untracked tutorials are not to be modified.

## Current scope
Approach B: generate schema-specific Gibbon ADTs and traversals from Python dataclass unions. Initial fields: signed 64-bit integers and recursive root-union references. Operations: sum_ints and add_ints(runtime amount); retain packed handles and return new values, do not mutate inputs. No arbitrary callbacks, strings, containers, cycles, alias preservation, parallel execution, or generic fold algebra.

## Initial work allocations
- native pupil owns python-kernels/spikes/native/ only, plus local compiler build artifacts. Establish runnable native integration, or concrete build blocker and minimal required changes. No core source edits without advisor approval.
- layout pupil owns python-kernels/spikes/layout/ only. Trace actual packed file and live-region representations, ownership and GC; write grounded report and any small standalone tests. No whole compiler builds to avoid contention with native pupil.
- schema pupil owns python-kernels/frontend/ only. Build minimal schema extraction and deterministic Gibbon source generation with test-first unittest tests; compile verification waits for native toolchain results. No byte layout or FFI implementation.

No pupil may edit another pupil's area, change global Hermes configuration, spawn more agents, commit, push, or publish. Capture exact commands/results and blockers, not fabricated outputs. New source code follows test-first development. Keep implementation readable and small. Reports must distinguish generated source tests from actual compiled Gibbon/native execution.

## Integration decisions reserved for advisor
- Actual integer and constructor encoding.
- Flat interchange representation versus runtime region representation.
- Stable exported wrapper signatures and allocation/rooting rules.
- Multiple schema libraries versus one combined module, including symbol collision handling.

## Status
Advisor verified a runnable restricted two-schema API: compile_type -> pack -> native sum/add -> retained output -> unpack. Integration suite (7 tests), frontend suite (9 tests), and native bridge suite (3 tests) passed. Both schema libraries coexist; 60 seeded random fixtures compared to Python reference operations. Runnable demo and actual limits are documented in python-kernels/README.md. Advisor reran benchmarks on five balanced/skewed fixtures and documented real samples in integration/benchmark-results.json and interpretation in integration/BENCHMARK.md. Retained native execution was faster in this exploratory run, but conversion dominated and initial-pack end-to-end sequences did not beat Python. Compilation cache, fresh checkout bootstrap, memory stress and portable/general region support are not complete. Initial native/codec contract is flat host-native fixed-shape caller-owned buffers, not arbitrary chunked runtime regions.
