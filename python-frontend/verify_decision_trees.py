"""Native mixed packed-tree/vector regressions; run in Vulcan's existing shell.

Execute only trusted fixtures under CPython as references. Float results allow
float32 rounding/printing error; these tests do not promise float64 equivalence.
"""
import argparse
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import types
from translate import translate


def cases():
    source = (Path(__file__).parent / 'examples/decision_tree.py').read_text()
    prefix = source[:source.index('\ndef main()')]
    result = [('decision_tree', source, False)]
    for name, values in (
        ('left_left', '[-2.0, -1.0]'),
        ('left_right', '[1.0, 0.0]'),
        ('right', '[2.0, 5.0]'),
        ('threshold_equal', '[1.5, -0.5]'),
        ('empty_features_unused_leaf', '[]'),
    ):
        # Empty literal defaults to list[int]; use float repetition for this case.
        if name == 'empty_features_unused_leaf':
            program = prefix + '\ndef main() -> float:\n    features = [0.0] * 0\n    return predict(Leaf(8.5), features)\n'
        else:
            program = source.replace('[1.0, 0.0]', values)
        result.append((name, program, False))
    result.extend([
        ('right_short_vector', source.replace('[1.0, 0.0]', '[2.0]'), False),
        ('negative_feature', source.replace('Split(0, 1.5,', 'Split(-1, 1.5,'), False),
        ('leaf_only', source.replace('tree = model()', 'tree = Leaf(-3.5)'), False),
        ('reuse_model', prefix + '''
def main() -> float:
    tree = model()
    first = [-2.0, -1.0]
    second = [1.0, 0.0]
    third = [2.0, 5.0]
    return predict(tree, first) + predict(tree, second) + predict(tree, third)
''', False),
        ('caller_updates_between_predictions', prefix + '''
def main() -> float:
    tree = model()
    features = [-1.0, 0.0]
    total = 0.0
    value = -1.0
    for i in range(5):
        features[0] = value
        total = total + predict(tree, features)
        value = value + 1.0
    return total
''', False),
        ('float_vector_math', '''def twice(xs: list[float]) -> float:
    return xs[0] * 2.0

def main() -> float:
    xs = [0.5] * 3
    xs[-1] = -1.25
    return twice(xs) + xs[-1] - 0.5
''', False),
        ('float_inequality', '''def main() -> bool:
    return 1.0 != 2.0
''', False),
        ('float_inequality_equal', '''def main() -> bool:
    return 2.0 != 2.0
''', False),
        ('float_rounding', '''def main() -> float:
    values = [0.1, 0.2]
    return values[0] + values[1]
''', False),
        ('readonly_int_parameter', '''def first(values: list[int]) -> int:
    return values[-1]

def main() -> int:
    values = [1, 2, 3]
    return first(values)
''', False),
        ('integer_classification', source.replace('value: float', 'value: int').replace('-> float:', '-> int:').replace('Leaf(-1.25)', 'Leaf(-1)').replace('Leaf(2.5)', 'Leaf(2)').replace('Leaf(4.75)', 'Leaf(4)'), False),
        ('feature_high', source.replace('[1.0, 0.0]', '[1.0]'), True),
        ('feature_low', source.replace('Split(0, 1.5,', 'Split(-3, 1.5,'), True),
        ('feature_empty', source.replace('[1.0, 0.0]', '[0.0] * 0'), True),
    ])
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--gibbon', required=True, type=Path)
    parser.add_argument('--gibbon-root', required=True, type=Path)
    args = parser.parse_args()
    build = Path(__file__).resolve().parent / 'build/decision-trees'
    build.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, GIBBONDIR=str(args.gibbon_root.resolve()))
    records = []
    for name, source, fails in cases():
        module = types.ModuleType('reference_decision_' + name)
        sys.modules[module.__name__] = module
        exec(compile(source, name + '.py', 'exec'), module.__dict__)
        try:
            expected = module.main()
        except IndexError:
            assert fails, name
            expected = None
        else:
            assert not fails, name
        hs = build / (name + '.hs')
        hs.write_text(translate(source, name + '.py'))
        command = [str(args.gibbon.resolve()), '--hs', '--packed', '--cc=gcc', '--to-exe', str(hs)]
        compile_run = subprocess.run(command, env=env, capture_output=True, text=True, timeout=180)
        (build / (name + '.compile.log')).write_text(compile_run.stdout + compile_run.stderr)
        if compile_run.returncode:
            raise RuntimeError(f'{name}: compilation failed; see {name}.compile.log\n{compile_run.stderr[-3000:]}')
        run = subprocess.run([str(hs.with_suffix('.exe'))], env=env, capture_output=True, text=True, timeout=15)
        raw = run.stdout.strip()
        if fails:
            assert run.returncode != 0 and 'list index out of bounds' in run.stdout + run.stderr, (name, run)
            observed = 'bounds failure'
        else:
            assert run.returncode == 0, (name, run.stderr)
            if type(expected) is bool:
                observed = {'True': True, 'False': False, '#t': True, '#f': False}.get(raw)
                assert observed is expected, (name, expected, raw)
            elif type(expected) is int:
                observed = int(raw)
                assert expected == observed, (name, expected, raw)
            else:
                observed = float(raw)
                assert math.isfinite(observed) and math.isclose(observed, expected, rel_tol=2e-6, abs_tol=2e-6), (name, expected, raw)
        records.append(dict(case=name, expected=expected, observed=observed, expected_bounds_failure=fails,
                            native_returncode=run.returncode, generated_source=str(hs), extra_flags=[]))
        (build / 'results.json').write_text(json.dumps(records, indent=2) + '\n')
        print(f'{name}: Python={expected}, Gibbon={observed} PASS', flush=True)
    good = sum(not r['expected_bounds_failure'] for r in records)
    print(f'{good} decision-tree/float/vector native comparisons and {len(records) - good} bounds failures passed')


if __name__ == '__main__':
    main()
