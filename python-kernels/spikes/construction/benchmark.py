"""Exploratory construction timings; compilation excluded, results checked outside timing."""
import gc
import json
import statistics
import time
from pathlib import Path
from construction import ConstructionOps
import readme_tree
from api import compile_type


def main():
    native = ConstructionOps()
    oracle = compile_type(readme_tree.Tree, vars(readme_tree), name='Tree', sum_constructors=('Leaf',))
    rows = []
    for depth in (5, 10, 12):
        built = native.build_tree(depth)
        reference = oracle.pack(readme_tree.mk_tree(depth))
        assert built.to_bytes() == reference.to_bytes()
        # Private ABI compatibility check, not a supported public handle conversion.
        assert oracle._library.kernel_sum(built._data, len(built)) == 2 ** depth
        assert native.sum_leaves(built) == 2 ** depth
        row = {'depth': depth, 'nodes': 2 ** (depth + 1) - 1, 'bytes': len(built)}
        for label, fn in (
            ('native_build', lambda: native.build_tree(depth)),
            ('python_build_and_pack', lambda: oracle.pack(readme_tree.mk_tree(depth))),
        ):
            samples = []
            for _ in range(11):
                gc.collect()
                start = time.perf_counter_ns()
                result = fn()
                samples.append((time.perf_counter_ns() - start) / 1e6)
                assert result.to_bytes() == reference.to_bytes()
                del result
            row[label + '_ms'] = samples
            row[label + '_median_ms'] = statistics.median(samples)
        row['ratio'] = row['python_build_and_pack_median_ms'] / row['native_build_median_ms']
        rows.append(row)
    out = Path(__file__).with_name('benchmark-results.json')
    out.write_text(json.dumps(rows, indent=2) + '\n')
    print(json.dumps(rows, indent=2))


if __name__ == '__main__':
    main()
