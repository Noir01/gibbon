"""Measured Python/Gibbon fixed-layout expression benchmarks."""
from __future__ import annotations

import json
import platform
import statistics
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Union

from api import compile_type


@dataclass
class Lit:
    value: int


@dataclass
class Add:
    left: "Expr"
    right: "Expr"


Expr = Union[Lit, Add]
NAMESPACE = {"Lit": Lit, "Add": Add, "Expr": Expr}
REPS = 7
WARMUPS = 1


def fixture(depth: int, start: int = 1) -> Expr:
    if depth == 0:
        return Lit(start)
    return Add(fixture(depth - 1, start), fixture(depth - 1, start + 1))


def py_sum(node: Expr) -> int:
    if isinstance(node, Lit):
        return node.value
    return py_sum(node.left) + py_sum(node.right)


def py_add(node: Expr, amount: int) -> Expr:
    if isinstance(node, Lit):
        return Lit(node.value + amount)
    return Add(py_add(node.left, amount), py_add(node.right, amount))


def counts(node: Expr) -> tuple[int, int]:
    if isinstance(node, Lit):
        return 1, 1
    ln, ls = counts(node.left)
    rn, rs = counts(node.right)
    return 1 + ln + rn, ls + rs


def measure(fn, check, reps=REPS):
    for _ in range(WARMUPS):
        result = fn()
        check(result)
    samples = []
    for _ in range(reps):
        start = time.perf_counter_ns()
        result = fn()
        elapsed = time.perf_counter_ns() - start
        check(result)
        samples.append(elapsed)
    return {"median_ns": int(statistics.median(samples)), "samples_ns": samples,
            "repetitions": reps, "warmups": WARMUPS}


def skewed_fixture(depth):
    tree = Lit(1)
    for value in range(depth):
        tree = Add(tree, Lit(value))
    return tree


def main():
    rows = []
    def fresh_ops():
        return compile_type(Expr, NAMESPACE, name="Expr")
    # No application artifact cache: this is uncached compilation, not cold CPU/I/O.
    cold = measure(fresh_ops, lambda ops: None, reps=5)
    ops = fresh_ops()
    for shape, depth in (("balanced", 5), ("balanced", 9), ("balanced", 12),
                         ("skewed", 32), ("skewed", 96)):
        tree = fixture(depth) if shape == "balanced" else skewed_fixture(depth)
        nodes, scalars = counts(tree)
        reference_sum = py_sum(tree)
        amount = 2
        shifted = py_add(tree, amount)
        shifted_sum = py_sum(shifted)

        # One schema/library is reused across all values and shapes.
        packed = ops.pack(tree)
        assert ops.unpack(packed) == tree
        assert ops.sum_ints(packed) == reference_sum
        transformed = ops.add_ints(packed, amount)
        assert ops.unpack(transformed) == shifted
        assert ops.sum_ints(transformed) == shifted_sum

        def pack_once():
            return ops.pack(tree)

        pack_t = measure(pack_once, lambda p: assert_packed(p, ops, len(packed)))
        # Keep allocations inside the add operation measurement, matching API behavior.
        add_t = measure(lambda: ops.add_ints(packed, amount),
                        lambda p: assert_packed(p, ops, len(packed)))
        sum_t = measure(lambda: ops.sum_ints(packed),
                        lambda v: assert_value(v, reference_sum))
        unpack_t = measure(lambda: ops.unpack(packed),
                           lambda v: assert_value(v, tree))

        def end_to_end():
            p = ops.pack(tree)
            return ops.sum_ints(p)

        python_sum_t = measure(lambda: py_sum(tree),
                               lambda v: assert_value(v, reference_sum))
        python_add_t = measure(lambda: py_add(tree, amount),
                               lambda v: assert_value(v, shifted))
        e2e_t = measure(end_to_end, lambda v: assert_value(v, reference_sum))
        sequence_n = 3

        def native_sequence():
            p = packed
            for _ in range(sequence_n):
                p = ops.add_ints(p, amount)
            return ops.sum_ints(p)

        def python_sequence():
            value = tree
            for _ in range(sequence_n):
                value = py_add(value, amount)
            return py_sum(value)

        def packed_sequence_end_to_end():
            p = ops.pack(tree)
            for _ in range(sequence_n):
                p = ops.add_ints(p, amount)
            return ops.sum_ints(p)

        expected_sequence = python_sequence()
        assert native_sequence() == expected_sequence
        native_seq_t = measure(native_sequence,
                               lambda v: assert_value(v, expected_sequence))
        python_seq_t = measure(python_sequence,
                               lambda v: assert_value(v, expected_sequence))
        sequence_e2e_t = measure(packed_sequence_end_to_end,
                                 lambda v: assert_value(v, expected_sequence))
        rows.append({
            "shape": shape, "depth": depth, "nodes": nodes, "integer_scalars": scalars,
            "packed_bytes": len(packed), "transform_amount": amount,
            "sequence_additions": sequence_n,
            "reference_sum": reference_sum, "shifted_sum": shifted_sum,
            "sequence_sum": expected_sequence,
            "timings": {"cold_compile_type": cold, "pack": pack_t,
                        "native_sum": sum_t, "native_add_including_output_allocation": add_t,
                        "unpack": unpack_t, "pack_then_native_sum": e2e_t,
                        "native_repeated_add_then_sum": native_seq_t,
                        "python_sum": python_sum_t, "python_add": python_add_t,
                        "pack_then_native_sequence": sequence_e2e_t,
                        "python_repeated_add_then_sum": python_seq_t},
        })
    output = {
        "platform": platform.platform(), "machine": platform.machine(),
        "processor": platform.processor(), "python": sys.version,
        "timing_clock": "time.perf_counter_ns", "rows": rows,
        "notes": ["Flat host-specific fixed-shape native ABI; caller-owned Python arrays.",
                  "No claim of full RTS GC; transforms remain packed between calls.",
                  "Correctness assertions run outside individual timed intervals."],
    }
    path = Path(__file__).with_name("benchmark-results.json")
    path.write_text(json.dumps(output, indent=2) + "\n")
    print(path)


def assert_packed(value, ops, size):
    assert value._ops is ops and len(value) == size


def assert_value(value, expected):
    assert value == expected


if __name__ == "__main__":
    main()
