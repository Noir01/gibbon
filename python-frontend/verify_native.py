"""Compile real translated programs and compare with trusted Python fixtures."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import types


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--gibbon', required=True, type=Path)
    parser.add_argument('--gibbon-root', required=True, type=Path)
    args = parser.parse_args()
    from translate import translate
    here = Path(__file__).resolve().parent
    build = here / 'build'
    build.mkdir(exist_ok=True)
    env = dict(os.environ, GIBBONDIR=str(args.gibbon_root.resolve()))
    # Keep regression fixtures explicit: remote-only user experiments are preserved
    # by rsync and should not silently become mandatory test cases.
    fixture_names = (
        'bst', 'expression', 'fibonacci', 'histogram', 'irregular', 'loop',
        'loop_reverse', 'polynomial', 'predicate', 'scalar', 'tree', 'vector',
        'vector_literal', 'vector_order', 'vector_prefix',
        'accumulate', 'vector_postfix', 'vector_paths',
    )
    cases = [(name, (here / 'examples' / (name + '.py')).read_text()) for name in fixture_names]
    tree = (here / 'examples/tree.py').read_text()
    for depth, amount in [(0, 0), (1, -2), (4, 7)]:
        cases.append((f'tree_d{depth}_a{amount}', tree.replace('build(5)', f'build({depth})').replace('shift(tree, 4)', f'shift(tree, {amount})')))
    loop = (here / 'examples/loop.py').read_text()
    for size in (-3, 0, 1, 11):
        cases.append((f'loop_n{size}', loop.replace('accumulate(6)', f'accumulate({size})')))
    vector = (here / 'examples/vector.py').read_text()
    for size in (1, 3, 17):
        cases.append((f'vector_n{size}', vector.replace('size = 8', f'size = {size}')))
    for size in (0, -3):
        cases.append((f'vector_empty{size}', f'def main() -> int:\n    values = [5] * {size}\n    return len(values)\n'))
    cases.append(('range_snapshot', 'def main() -> int:\n    stop = 4\n    total = 0\n    for i in range(stop):\n        stop = 0\n        total += i\n    return total + stop\n'))
    cases.append(('predicate_false', (here / 'examples/predicate.py').read_text().replace('return True', 'return False')))
    cases.extend([
        ('literal_empty', 'def main() -> int:\n    values = []\n    return len(values)\n'),
        ('literal_single', 'def main() -> int:\n    values = [-9223372036854775808]\n    return values[-1]\n'),
        ('literal_snapshot', 'def main() -> int:\n    source = [1, 2]\n    copied = [source[0], source[0] + 1]\n    source[0] = 9\n    return copied[0] * 10 + copied[1]\n'),
    ])
    results = []
    for name, source in cases:
        # Execute only these trusted examples as the reference, never as translation.
        namespace = types.ModuleType(f'reference_{name}')
        import sys
        sys.modules[namespace.__name__] = namespace
        exec(compile(source, name + '.py', 'exec'), namespace.__dict__)
        expected = namespace.main()
        hs = build / (name + '.hs')
        hs.write_text(translate(source, filename=name + '.py'))
        # The BST currently trips Gibbon's copy-to-indirection path; retain copies.
        extra_flags = ['--no-rcopies'] if name == 'bst' else []
        command = [str(args.gibbon.resolve()), '--hs', '--packed', '--cc=gcc', '--to-exe', *extra_flags, str(hs)]
        compiled = subprocess.run(command, env=env, text=True, capture_output=True, timeout=180)
        (build / (name + '.compile.log')).write_text(compiled.stdout + compiled.stderr)
        if compiled.returncode:
            raise RuntimeError(f'{name}: compiler failed; see {build / (name + ".compile.log")}\n{compiled.stderr[-3000:]}')
        executable = hs.with_suffix('.exe')
        run = subprocess.run([str(executable)], env=env, text=True, capture_output=True, timeout=15, check=True)
        raw = run.stdout.strip()
        if type(expected) is bool:
            observed = {'True': True, 'False': False, '#t': True, '#f': False}.get(raw)
        else:
            if not re.fullmatch(r'-?\d+', raw):
                raise AssertionError(f'{name}: unexpected native output {raw!r}')
            observed = int(raw)
        assert observed == expected, (name, expected, raw)
        record = dict(case=name, expected=expected, observed=observed, generated_source=str(hs), executable=str(executable), extra_flags=extra_flags)
        results.append(record)
        (build / 'results.json').write_text(json.dumps(results, indent=2) + '\n')
        print(f'{name}: Python={expected}, Gibbon={observed} PASS', flush=True)
    print(f'{len(results)} native comparisons passed')


if __name__ == '__main__':
    main()
